from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission


class AdminPrincipalPermission(BasePermission):
    """Restrict an endpoint to active staff backed by Django's User model."""

    message = "An active admin account is required."

    def has_permission(self, request, view):
        user = request.user
        return (
            isinstance(user, get_user_model())
            and user.is_authenticated
            and user.is_active
            and user.is_staff
        )


class AdminModelPermission(BasePermission):
    """Apply explicitly declared Django model permissions per HTTP method."""

    def has_permission(self, request, view):
        required = getattr(view, "method_permissions", {}).get(request.method, ())
        return request.user.has_perms(required)


class AdminSuperuserPermission(BasePermission):
    message = "A superuser account is required."

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_superuser)
