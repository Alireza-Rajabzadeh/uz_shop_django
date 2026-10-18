from rest_framework.permissions import DjangoModelPermissions

from core.permissions import (  # noqa: F401
    AllRequiredPermissions,
    CustomActionPermission,
    MethodPermission,
)


class CatalogModelPermissions(DjangoModelPermissions):
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
        # A principal that is not a Django user (a vendor token that reached
        # here, for example) cannot hold catalog model permissions. Answer 403
        # instead of letting `has_perms` raise an AttributeError into a 500.
        if not hasattr(request.user, "has_perms"):
            return False
        return super().has_permission(request, view)

    def _queryset(self, view):
        model = getattr(view, "model", None)
        if model is not None:
            return model._default_manager.all()
        return super()._queryset(view)
