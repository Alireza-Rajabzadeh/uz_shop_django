from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from domains.customer.models import Customer, CustomerStatus, CustomerPreference


class CustomerAuthService:
    def register(self, validated_data):
        password = validated_data.pop("password")
        status = CustomerStatus.objects.filter(is_active=True).first()
        if not status:
            raise ValidationError("No active customer status available.")

        customer = Customer(**validated_data, status=status)
        customer.set_password(password)
        customer.save()

        CustomerPreference.objects.create(customer=customer)

        return self._build_auth_response(customer)

    def login(self, phone, password):
        try:
            customer = Customer.objects.get(phone=phone)
        except Customer.DoesNotExist:
            raise AuthenticationFailed("Invalid phone number or password.")

        if not customer.check_password(password):
            raise AuthenticationFailed("Invalid phone number or password.")

        if not customer.status.is_active:
            raise ValidationError("Account is inactive.")

        customer.last_login_at = timezone.now()
        customer.save(update_fields=["last_login_at"])

        return self._build_auth_response(customer)

    def update_profile(self, customer, validated_data):
        for attr, value in validated_data.items():
            setattr(customer, attr, value)
        customer.save()
        return self.get_profile(customer)

    def get_profile(self, customer):
        return {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "status": customer.status.title,
            "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
            "gender": customer.gender,
            "email_verified_at": customer.email_verified_at.isoformat() if customer.email_verified_at else None,
            "phone_verified_at": customer.phone_verified_at.isoformat() if customer.phone_verified_at else None,
            "created_at": customer.created_at.isoformat(),
        }

    def _build_auth_response(self, customer):
        refresh = RefreshToken.for_user(customer)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "customer": self.get_profile(customer),
        }
