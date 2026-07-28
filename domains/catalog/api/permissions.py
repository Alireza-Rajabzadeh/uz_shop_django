from rest_framework.permissions import DjangoModelPermissions, BasePermission


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


class MethodPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        mapping = getattr(view, "method_permissions", {})
        codename = mapping.get(request.method)
        if codename:
            return request.user.has_perm(codename)
        return True
