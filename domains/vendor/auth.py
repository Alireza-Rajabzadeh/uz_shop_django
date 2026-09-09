from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from .models import Vendor


class VendorJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None

    def get_user(self, validated_token):
        if validated_token.get("user_type") != "vendor":
            raise AuthenticationFailed("Invalid token type.")
        user_id = validated_token["user_id"]
        try:
            vendor = Vendor.objects.select_related("status").get(id=user_id)
        except Vendor.DoesNotExist as exc:
            raise AuthenticationFailed("Vendor not found.") from exc
        if not vendor.status.is_active:
            raise AuthenticationFailed("Vendor account is inactive.")
        if api_settings.CHECK_REVOKE_TOKEN and validated_token.get(
            api_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(vendor.password):
            raise AuthenticationFailed("The vendor's password has been changed.")
        return vendor
