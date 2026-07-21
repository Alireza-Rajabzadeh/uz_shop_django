from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from domains.customer.models import Customer


class CustomerAuthService:
    def register(self, validated_data):
        password = validated_data.pop("password")
        customer = Customer(**validated_data)
        customer.set_password(password)
        customer.save()
        return self._build_auth_response(customer)

    def login(self, phone, password):
        try:
            customer = Customer.objects.get(phone=phone)
        except Customer.DoesNotExist:
            raise AuthenticationFailed("Invalid phone number or password.")

        if not customer.check_password(password):
            raise AuthenticationFailed("Invalid phone number or password.")

        if not customer.is_active:
            raise ValidationError("Account is inactive.")

        return self._build_auth_response(customer)

    def get_profile(self, customer):
        return {
            "id": customer.id,
            "phone": customer.phone,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "is_active": customer.is_active,
            "created_at": customer.created_at.isoformat(),
        }

    def _build_auth_response(self, customer):
        refresh = RefreshToken.for_user(customer)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "customer": self.get_profile(customer),
        }
