from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class AdminJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        if validated_token.get("user_type") != "admin":
            raise AuthenticationFailed("Invalid token type.")
        return super().get_user(validated_token)
