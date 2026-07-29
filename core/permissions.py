from django.contrib.auth import get_user_model
from rest_framework.permissions import DjangoModelPermissions


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
