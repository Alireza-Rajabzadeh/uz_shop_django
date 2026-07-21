from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken


class AuthService:
    def authenticate_admin(self, username, password):
        user = authenticate(username=username, password=password)

        if user is None:
            raise AuthenticationFailed("Invalid username or password.")

        if not user.is_active:
            raise ValidationError("User account is inactive.")

        if not user.is_staff:
            raise PermissionDenied("You do not have permission to access this resource.")

        return self._generate_token_response(user)

    def _generate_token_response(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
        }
