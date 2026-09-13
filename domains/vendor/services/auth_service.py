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
from domains.vendor.models import Vendor, VendorPreference
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum

logger = logging.getLogger(__name__)


class VendorConfirmationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class VendorConfirmationThrottled(VendorConfirmationError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__({"detail": [_("Please wait before requesting another code.")]})


class VendorConfirmationUnavailable(VendorConfirmationError):
    pass


class VendorAuthService:
    def request_registration(self, validated_data, ttl=120):
        password = validated_data.pop("password")
        validated_data.pop("password_confirmation")

        vendor = Vendor(**validated_data, status_id=VendorStatusEnum.PENDING.value)
        vendor.set_password(password)
        vendor.save()

        VendorPreference.objects.create(vendor=vendor)

        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="vendor_register",
                subject=vendor.pk,
                payload={
                    "vendor_id": vendor.pk,
                    "credential_fingerprint": self._credential_fingerprint(vendor),
                },
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise VendorConfirmationThrottled(exc.retry_after) from exc

        message = _(
            "Your UzShop registration confirmation code is %(code)s. "
            "It expires in %(minutes)s minutes."
        ) % {
            "code": generated.code,
            "minutes": max(generated.expires_in // 60, 1),
        }

        self._queue_sms(vendor.pk, message, generated.expires_at)

        now = timezone.now()
        remaining_ttl = max(int((generated.expires_at - now).total_seconds()), 0)
        resend_after = max(int((generated.resend_at - now).total_seconds()), 0)
        return {
            "request_id": generated.request_id,
            "expires_in": remaining_ttl,
            "resend_after": resend_after,
            "destination": self._mask_phone(vendor.phone),
        }

    def confirm_registration(self, request_id, code):
        try:
            payload = ConfirmedRequestService().get_code(
                request_id=request_id,
                code=code,
                purpose="vendor_register",
            )
        except ConfirmedRequestInvalid as exc:
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc

        try:
            vendor = Vendor.objects.select_related("status").get(
                pk=payload["vendor_id"]
            )
        except (Vendor.DoesNotExist, KeyError, TypeError):
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )

        if payload.get("credential_fingerprint") != self._credential_fingerprint(vendor):
            raise VendorConfirmationError(
                {"code": [_("The confirmation request is no longer valid.")]}
            )
        if vendor.status_id != VendorStatusEnum.PENDING.value:
            raise VendorConfirmationError(
                {"detail": [_("Account is not pending confirmation.")]}
            )

        with transaction.atomic():
            vendor = Vendor.objects.select_for_update().select_related("status").get(
                pk=vendor.pk
            )
            if vendor.status_id != VendorStatusEnum.PENDING.value:
                raise VendorConfirmationError(
                    {"detail": [_("Account is not pending confirmation.")]}
                )
            vendor.status_id = VendorStatusEnum.ACTIVE.value
            vendor.last_login = timezone.now()
            vendor.save(update_fields=["status", "last_login", "updated_at"])

        return self._build_auth_response(vendor)

    def request_login_confirmation(self, phone, password, ttl=120):
        vendor = self._authenticate_vendor(phone, password)
        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="vendor_login",
                subject=vendor.pk,
                payload={
                    "vendor_id": vendor.pk,
                    "credential_fingerprint": self._credential_fingerprint(vendor),
                },
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise VendorConfirmationThrottled(exc.retry_after) from exc

        message = _(
            "Your UzShop login confirmation code is %(code)s. "
            "It expires in %(minutes)s minutes."
        ) % {
            "code": generated.code,
            "minutes": max(generated.expires_in // 60, 1),
        }

        self._queue_sms(vendor.pk, message, generated.expires_at)

        now = timezone.now()
        remaining_ttl = max(int((generated.expires_at - now).total_seconds()), 0)
        resend_after = max(int((generated.resend_at - now).total_seconds()), 0)
        if remaining_ttl <= 0:
            confirmed_requests.cancel(generated.request_id)
            raise VendorConfirmationUnavailable(
                {"detail": [_("The confirmation code could not be sent.")]}
            )
        return {
            "request_id": generated.request_id,
            "expires_in": remaining_ttl,
            "resend_after": resend_after,
            "destination": self._mask_phone(vendor.phone),
        }

    def confirm_login(self, request_id, code):
        try:
            payload = ConfirmedRequestService().get_code(
                request_id=request_id,
                code=code,
                purpose="vendor_login",
            )
        except ConfirmedRequestInvalid as exc:
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc

        try:
            vendor = Vendor.objects.select_related("status").get(
                pk=payload["vendor_id"]
            )
        except (Vendor.DoesNotExist, KeyError, TypeError):
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )

        if payload.get("credential_fingerprint") != self._credential_fingerprint(vendor):
            raise VendorConfirmationError(
                {"code": [_("The confirmation request is no longer valid.")]}
            )
        if not vendor.status.is_active:
            raise VendorConfirmationError({"detail": [_("Account is inactive.")]})

        vendor.last_login = timezone.now()
        vendor.save(update_fields=["last_login"])
        return self._build_auth_response(vendor)

    def request_phone_confirmation(self, vendor, ttl=120):
        if vendor.phone_verified_at is not None:
            raise VendorConfirmationError(
                {"detail": [_("Phone number is already verified.")]}
            )
        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="vendor_phone_verification",
                subject=vendor.pk,
                payload={"vendor_id": vendor.pk, "phone": vendor.phone},
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise VendorConfirmationThrottled(exc.retry_after) from exc

        message = _(
            "Your UzShop phone verification code is %(code)s. "
            "It expires in %(minutes)s minutes."
        ) % {
            "code": generated.code,
            "minutes": max(generated.expires_in // 60, 1),
        }

        self._queue_sms(vendor.pk, message, generated.expires_at)

        now = timezone.now()
        return {
            "request_id": generated.request_id,
            "expires_in": max(int((generated.expires_at - now).total_seconds()), 0),
            "resend_after": max(int((generated.resend_at - now).total_seconds()), 0),
            "destination": self._mask_phone(vendor.phone),
        }

    def confirm_phone(self, vendor, request_id, code):
        confirmed_requests = ConfirmedRequestService()
        try:
            payload = confirmed_requests.check_code(
                request_id=request_id,
                code=code,
                purpose="vendor_phone_verification",
            )
        except ConfirmedRequestInvalid as exc:
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc
        if payload.get("vendor_id") != vendor.pk or payload.get("phone") != vendor.phone:
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )

        with transaction.atomic():
            vendor = Vendor.objects.select_for_update().select_related("status").get(
                pk=vendor.pk
            )
            if not vendor.status.is_active or vendor.phone != payload["phone"]:
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            try:
                confirmed_requests.get_code(
                    request_id=request_id,
                    code=code,
                    purpose="vendor_phone_verification",
                )
            except ConfirmedRequestInvalid as exc:
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                ) from exc
            if vendor.phone_verified_at is None:
                vendor.phone_verified_at = timezone.now()
                vendor.save(update_fields=["phone_verified_at", "updated_at"])
        return self.get_profile(vendor)

    def request_password_reset(self, phone, ttl=120):
        vendor = Vendor.objects.select_related("status").filter(phone=phone).first()
        eligible = vendor is not None and vendor.status.is_active
        payload = {"eligible": eligible}
        if eligible:
            payload.update({
                "vendor_id": vendor.pk,
                "credential_fingerprint": self._credential_fingerprint(vendor),
            })

        confirmed_requests = ConfirmedRequestService()
        try:
            generated = confirmed_requests.generate_code(
                purpose="vendor_password_reset",
                subject=phone,
                payload=payload,
                ttl=ttl,
            )
        except ConfirmedRequestThrottled as exc:
            raise VendorConfirmationThrottled(exc.retry_after) from exc

        message = _(
            "Your UzShop password reset code is %(code)s. "
            "It expires in %(minutes)s minutes."
        ) % {
            "code": generated.code,
            "minutes": max(generated.expires_in // 60, 1),
        }

        from domains.vendor.tasks import deliver_vendor_sms

        try:
            deliver_vendor_sms.apply_async(
                args=[
                    vendor.pk if eligible else None,
                    message,
                    generated.expires_at.isoformat(),
                ],
                expires=generated.expires_at,
            )
        except Exception:
            logger.exception("Could not queue a vendor password reset delivery task")

        return {
            "request_id": generated.request_id,
            "expires_in": generated.expires_in,
            "resend_after": generated.resend_after,
            "destination": self._mask_phone(phone),
        }

    def reset_password(self, request_id, code, new_password):
        confirmed_requests = ConfirmedRequestService()
        try:
            payload = confirmed_requests.check_code(
                request_id=request_id,
                code=code,
                purpose="vendor_password_reset",
            )
        except ConfirmedRequestInvalid as exc:
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            ) from exc

        if not payload.get("eligible"):
            confirmed_requests.get_code(
                request_id=request_id,
                code=code,
                purpose="vendor_password_reset",
            )
            raise VendorConfirmationError(
                {"code": [_("The confirmation code is invalid or expired.")]}
            )
        with transaction.atomic():
            try:
                vendor = Vendor.objects.select_related("status").select_for_update().get(
                    pk=payload["vendor_id"]
                )
            except (Vendor.DoesNotExist, KeyError, TypeError):
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            if not vendor.status.is_active:
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            if payload.get("credential_fingerprint") != self._credential_fingerprint(vendor):
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                )
            try:
                validate_password(new_password, user=vendor)
            except DjangoValidationError as exc:
                raise VendorConfirmationError({"new_password": exc.messages}) from exc
            try:
                confirmed_requests.get_code(
                    request_id=request_id,
                    code=code,
                    purpose="vendor_password_reset",
                )
            except ConfirmedRequestInvalid as exc:
                raise VendorConfirmationError(
                    {"code": [_("The confirmation code is invalid or expired.")]}
                ) from exc
            vendor.set_password(new_password)
            vendor.phone_verified_at = timezone.now()
            vendor.save(update_fields=["password", "phone_verified_at", "updated_at"])

    @staticmethod
    def _authenticate_vendor(phone, password):
        try:
            vendor = Vendor.objects.select_related("status").get(phone=phone)
        except Vendor.DoesNotExist:
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not vendor.check_password(password):
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not vendor.status.is_active:
            raise ValidationError(_("Account is inactive."))

        if vendor.status_id != VendorStatusEnum.ACTIVE.value:
            raise ValidationError(_("Account is not active."))

        return vendor

    @staticmethod
    def _credential_fingerprint(vendor):
        return salted_hmac("vendor-login-confirmation", vendor.password).hexdigest()

    @staticmethod
    def _mask_phone(phone):
        if len(phone) <= 8:
            return "*" * len(phone)
        return f"{phone[:4]}{'*' * (len(phone) - 8)}{phone[-4:]}"

    @staticmethod
    def _queue_sms(vendor_id, message, expires_at):
        from domains.vendor.tasks import deliver_vendor_sms

        try:
            deliver_vendor_sms.apply_async(
                args=[vendor_id, message, expires_at.isoformat()],
                expires=expires_at,
            )
        except Exception:
            logger.exception("Could not queue SMS delivery for vendor %s", vendor_id)

    def update_profile(self, vendor, validated_data):
        for attr, value in validated_data.items():
            setattr(vendor, attr, value)
        vendor.save()
        return self.get_profile(vendor)

    def change_password(self, vendor, current_password, new_password):
        if not vendor.check_password(current_password):
            raise ValidationError({
                "current_password": _("The current password is incorrect.")
            })

        try:
            validate_password(new_password, user=vendor)
        except DjangoValidationError as exc:
            raise ValidationError({"new_password": exc.messages}) from exc

        vendor.set_password(new_password)
        vendor.save(update_fields=["password"])

    def get_profile(self, vendor):
        return {
            "id": vendor.id,
            "vendor_code": vendor.vendor_code,
            "first_name": vendor.first_name,
            "last_name": vendor.last_name,
            "email": vendor.email,
            "phone": vendor.phone,
            "national_id": vendor.national_id,
            "status_title": vendor.status.title,
            "date_of_birth": vendor.date_of_birth.isoformat() if vendor.date_of_birth else None,
            "gender": vendor.gender,
            "email_verified_at": vendor.email_verified_at.isoformat() if vendor.email_verified_at else None,
            "phone_verified_at": vendor.phone_verified_at.isoformat() if vendor.phone_verified_at else None,
            "created_at": vendor.created_at.isoformat(),
        }

    def _build_auth_response(self, vendor):
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "vendor": self.get_profile(vendor),
        }
