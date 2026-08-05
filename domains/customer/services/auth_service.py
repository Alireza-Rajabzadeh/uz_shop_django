import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext as _
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from core.services import (
    ConfirmedRequestInvalid,
    ConfirmedRequestService,
    ConfirmedRequestThrottled,
)
from domains.customer.models import Customer, CustomerPreference
from domains.customer.enums.CustomerStatusEnum import CustomerStatusEnum
from domains.notifications.services import NotificationError, SMSService

logger = logging.getLogger(__name__)


class CustomerConfirmationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class CustomerConfirmationThrottled(CustomerConfirmationError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__({"detail": [_("Please wait before requesting another code.")]})


class CustomerConfirmationUnavailable(CustomerConfirmationError):
    pass


class CustomerAuthService:
    def register(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password_confirmation")

        customer = Customer(**validated_data, status_id=CustomerStatusEnum.ACTIVE.value)
        customer.set_password(password)
        customer.save()

        CustomerPreference.objects.create(customer=customer)

        return self._build_auth_response(customer)

    def request_login_confirmation(self, phone, password, ttl=120):
        customer = self._authenticate_customer(phone, password)
        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="customer_login",
                subject=customer.pk,
                payload={
                    "customer_id": customer.pk,
                    "credential_fingerprint": self._credential_fingerprint(customer),
                },
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise CustomerConfirmationThrottled(exc.retry_after) from exc

        try:
            notification = SMSService().send(
                receiver=customer.phone,
                message=_(
                    "Your UzShop login confirmation code is %(code)s. "
                    "It expires in %(minutes)s minutes."
                ) % {
                    "code": generated.code,
                    "minutes": max(generated.expires_in // 60, 1),
                },
                sensitive=True,
                expires_at=generated.expires_at,
            )
        except NotificationError as exc:
            confirmed_requests.cancel(generated.request_id)
            raise CustomerConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            ) from exc
        if notification.status == "failed":
            confirmed_requests.cancel(generated.request_id)
            raise CustomerConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            )

        now = timezone.now()
        remaining_ttl = max(int((generated.expires_at - now).total_seconds()), 0)
        resend_after = max(int((generated.resend_at - now).total_seconds()), 0)
        if remaining_ttl <= 0:
            confirmed_requests.cancel(generated.request_id)
            raise CustomerConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            )
        return {
            "request_id": generated.request_id,
            "expires_in": remaining_ttl,
            "resend_after": resend_after,
            "destination": self._mask_phone(customer.phone),
        }

    def confirm_login(self, request_id, code):
        try:
            payload = ConfirmedRequestService().get_code(
                request_id=request_id,
                code=code,
                purpose="customer_login",
            )
        except ConfirmedRequestInvalid as exc:
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc

        try:
            customer = Customer.objects.select_related("status").get(
                pk=payload["customer_id"]
            )
        except (Customer.DoesNotExist, KeyError, TypeError):
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )

        if payload.get("credential_fingerprint") != self._credential_fingerprint(customer):
            raise CustomerConfirmationError(
                {"code": [_("The confirmation request is no longer valid.")]}
            )
        if not customer.status.is_active:
            raise CustomerConfirmationError({"detail": [_("Account is inactive.")]})

        customer.last_login = timezone.now()
        customer.save(update_fields=["last_login"])
        return self._build_auth_response(customer)

    def request_phone_confirmation(self, customer, ttl=120):
        if customer.phone_verified_at is not None:
            raise CustomerConfirmationError(
                {"detail": [_("Phone number is already verified.")]}
            )
        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="customer_phone_verification",
                subject=customer.pk,
                payload={"customer_id": customer.pk, "phone": customer.phone},
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise CustomerConfirmationThrottled(exc.retry_after) from exc

        try:
            notification = SMSService().send(
                receiver=customer.phone,
                message=_(
                    "Your UzShop phone verification code is %(code)s. "
                    "It expires in %(minutes)s minutes."
                ) % {
                    "code": generated.code,
                    "minutes": max(generated.expires_in // 60, 1),
                },
                sensitive=True,
                expires_at=generated.expires_at,
            )
        except NotificationError as exc:
            confirmed_requests.cancel(generated.request_id)
            raise CustomerConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            ) from exc
        if notification.status == "failed":
            confirmed_requests.cancel(generated.request_id)
            raise CustomerConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            )

        now = timezone.now()
        return {
            "request_id": generated.request_id,
            "expires_in": max(int((generated.expires_at - now).total_seconds()), 0),
            "resend_after": max(int((generated.resend_at - now).total_seconds()), 0),
            "destination": self._mask_phone(customer.phone),
        }

    def confirm_phone(self, customer, request_id, code):
        confirmed_requests = ConfirmedRequestService()
        try:
            payload = confirmed_requests.check_code(
                request_id=request_id,
                code=code,
                purpose="customer_phone_verification",
            )
        except ConfirmedRequestInvalid as exc:
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc
        if payload.get("customer_id") != customer.pk or payload.get("phone") != customer.phone:
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )

        with transaction.atomic():
            customer = Customer.objects.select_for_update().select_related("status").get(
                pk=customer.pk
            )
            if not customer.status.is_active or customer.phone != payload["phone"]:
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            try:
                confirmed_requests.get_code(
                    request_id=request_id,
                    code=code,
                    purpose="customer_phone_verification",
                )
            except ConfirmedRequestInvalid as exc:
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                ) from exc
            if customer.phone_verified_at is None:
                customer.phone_verified_at = timezone.now()
                customer.save(update_fields=["phone_verified_at", "updated_at"])
        return self.get_profile(customer)

    def request_password_reset(self, phone, ttl=120):
        customer = Customer.objects.select_related("status").filter(phone=phone).first()
        eligible = customer is not None and customer.status.is_active
        payload = {"eligible": eligible}
        if eligible:
            payload.update({
                "customer_id": customer.pk,
                "credential_fingerprint": self._credential_fingerprint(customer),
            })

        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="customer_password_reset",
                subject=phone,
                payload=payload,
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise CustomerConfirmationThrottled(exc.retry_after) from exc

        from domains.customer.tasks import deliver_password_reset_sms

        try:
            deliver_password_reset_sms.apply_async(
                args=[
                    customer.pk if eligible else None,
                    generated.code,
                    generated.expires_at.isoformat(),
                ],
                expires=generated.expires_at,
            )
        except Exception:
            logger.exception("Could not queue a customer password reset delivery task")

        return {
            "request_id": generated.request_id,
            "expires_in": generated.expires_in,
            "resend_after": generated.resend_after,
            "destination": self._mask_phone(phone),
        }

    def deliver_password_reset_code(self, customer_id, code, expires_at):
        if customer_id is None or expires_at <= timezone.now():
            return
        customer = Customer.objects.select_related("status").filter(
            pk=customer_id,
            status__is_active=True,
        ).first()
        if customer is None:
            return
        try:
            SMSService().send(
                receiver=customer.phone,
                message=_(
                    "Your UzShop password reset code is %(code)s. "
                    "It expires in %(minutes)s minutes."
                ) % {
                    "code": code,
                    "minutes": max(int((expires_at - timezone.now()).total_seconds()) // 60, 1),
                },
                sensitive=True,
                expires_at=expires_at,
            )
        except NotificationError:
            logger.warning(
                "Password reset SMS could not be created for customer %s", customer.pk
            )

    def reset_password(self, request_id, code, new_password):
        confirmed_requests = ConfirmedRequestService()
        try:
            payload = confirmed_requests.check_code(
                request_id=request_id,
                code=code,
                purpose="customer_password_reset",
            )
        except ConfirmedRequestInvalid as exc:
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc

        if not payload.get("eligible"):
            confirmed_requests.get_code(
                request_id=request_id,
                code=code,
                purpose="customer_password_reset",
            )
            raise CustomerConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )
        with transaction.atomic():
            try:
                customer = Customer.objects.select_related("status").select_for_update().get(
                    pk=payload["customer_id"]
                )
            except (Customer.DoesNotExist, KeyError, TypeError):
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            if not customer.status.is_active:
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            if payload.get("credential_fingerprint") != self._credential_fingerprint(customer):
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            try:
                validate_password(new_password, user=customer)
            except DjangoValidationError as exc:
                raise CustomerConfirmationError({"new_password": exc.messages}) from exc
            try:
                confirmed_requests.get_code(
                    request_id=request_id,
                    code=code,
                    purpose="customer_password_reset",
                )
            except ConfirmedRequestInvalid as exc:
                raise CustomerConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                ) from exc
            customer.set_password(new_password)
            customer.phone_verified_at = timezone.now()
            customer.save(update_fields=["password", "phone_verified_at", "updated_at"])

    @staticmethod
    def _authenticate_customer(phone, password):
        try:
            customer = Customer.objects.select_related("status").get(phone=phone)
        except Customer.DoesNotExist:
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not customer.check_password(password):
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not customer.status.is_active:
            raise ValidationError(_("Account is inactive."))

        return customer

    @staticmethod
    def _credential_fingerprint(customer):
        return salted_hmac("customer-login-confirmation", customer.password).hexdigest()

    @staticmethod
    def _mask_phone(phone):
        if len(phone) <= 8:
            return "*" * len(phone)
        return f"{phone[:4]}{'*' * (len(phone) - 8)}{phone[-4:]}"

    def update_profile(self, customer, validated_data):
        for attr, value in validated_data.items():
            setattr(customer, attr, value)
        customer.save()
        return self.get_profile(customer)

    def change_password(self, customer, current_password, new_password):
        if not customer.check_password(current_password):
            raise ValidationError({
                "current_password": _("The current password is incorrect.")
            })

        try:
            validate_password(new_password, user=customer)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": exc.messages}) from exc

        customer.set_password(new_password)
        customer.save(update_fields=["password"])

    def get_profile(self, customer):
        return {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "status_title": customer.status.title,
            "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
            "gender": customer.gender,
            "email_verified_at": customer.email_verified_at.isoformat() if customer.email_verified_at else None,
            "phone_verified_at": customer.phone_verified_at.isoformat() if customer.phone_verified_at else None,
            "created_at": customer.created_at.isoformat(),
        }

    def _build_auth_response(self, customer):
        refresh = RefreshToken.for_user(customer)
        refresh["user_type"] = "customer"
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "customer": self.get_profile(customer),
        }
