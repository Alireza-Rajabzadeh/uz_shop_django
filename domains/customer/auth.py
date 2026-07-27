from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Customer


class CustomerJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None

    def get_user(self, validated_token):
        if validated_token.get("user_type") != "customer":
            raise AuthenticationFailed("Invalid token type.")
        user_id = validated_token["user_id"]
        try:
            return Customer.objects.get(id=user_id)
        except Customer.DoesNotExist as exc:
            raise AuthenticationFailed("Customer not found.") from exc
