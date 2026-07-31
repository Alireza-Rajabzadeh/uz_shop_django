from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from domains.customer.models import Customer, CustomerPreference
from domains.customer.enums.CustomerStatusEnum import CustomerStatusEnum


class CustomerAuthService:
    def register(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password_confirmation")

        customer = Customer(**validated_data, status_id=CustomerStatusEnum.ACTIVE.value)
        customer.set_password(password)
        customer.save()

        CustomerPreference.objects.create(customer=customer)

        return self._build_auth_response(customer)

    def login(self, phone, password):
        try:
            customer = Customer.objects.get(phone=phone)
        except Customer.DoesNotExist:
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not customer.check_password(password):
            raise AuthenticationFailed(_("Invalid phone number or password."))

        if not customer.status.is_active:
            raise ValidationError(_("Account is inactive."))

        customer.last_login = timezone.now()
        customer.save(update_fields=["last_login"])

        return self._build_auth_response(customer)

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
