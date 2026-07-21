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
        user_id = validated_token["user_id"]
        return Customer.objects.get(id=user_id)
