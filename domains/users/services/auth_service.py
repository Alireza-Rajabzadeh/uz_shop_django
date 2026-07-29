from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.utils.translation import gettext as _
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from domains.users.serializers.profile import AdminProfileSerializer


class AuthService:
    def authenticate_admin(self, username, password):
        user = authenticate(username=username, password=password)

        if user is None:
            raise AuthenticationFailed(_("Invalid username or password."))

        if not user.is_active:
            raise ValidationError(_("User account is inactive."))

        if not user.is_staff:
            raise PermissionDenied(_("You do not have permission to access this resource."))

        update_last_login(None, user)
        return self._generate_token_response(user)

    def _generate_token_response(self, user):
        refresh = RefreshToken.for_user(user)
        refresh["user_type"] = "admin"
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                **AdminProfileSerializer(user).data,
                "permissions": sorted(user.get_all_permissions()),
            },
        }
