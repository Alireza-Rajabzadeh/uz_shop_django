from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission, DjangoModelPermissions


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        from domains.customer.models import Customer

        return isinstance(request.user, Customer)


class AdminModelPermissions(DjangoModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }

    def has_permission(self, request, view):
        if not (
            isinstance(request.user, get_user_model())
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
        ):
            return False
        return super().has_permission(request, view)

    def _queryset(self, view):
        model = getattr(view, "model", None)
        if model is not None:
            return model._default_manager.all()
        return super()._queryset(view)


class CustomActionPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        perms = getattr(view, "required_permissions", None)
        if perms is not None:
            return any(request.user.has_perm(perm) for perm in perms)
        perm = getattr(view, "required_permission", None)
        if perm is None:
            return True
        return request.user.has_perm(perm)


class AllRequiredPermissions(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return all(
            request.user.has_perm(permission)
            for permission in getattr(view, "required_permissions", ())
        )


class MethodPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        mapping = getattr(view, "method_permissions", {})
        codename = mapping.get(request.method)
        if codename:
            return request.user.has_perm(codename)
        return True
