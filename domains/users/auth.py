from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class AdminJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        if validated_token.get("user_type") != "admin":
            raise AuthenticationFailed("Invalid token type.")
        user = super().get_user(validated_token)
        if not user.is_active or not user.is_staff:
            raise AuthenticationFailed("Admin account is inactive or no longer staff.")
        return user
