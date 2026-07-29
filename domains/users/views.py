from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.models import Count, Q
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.responses import api_response
from .auth import AdminJWTAuthentication
from .permissions import (
    AdminModelPermission,
    AdminPrincipalPermission,
    AdminSuperuserPermission,
)
from .serializers import (
    AdminAssignmentSerializer,
    AdminLoginSerializer,
    AdminPasswordChangeSerializer,
    AdminProfileSerializer,
    AdminProfileUpdateSerializer,
    AdminSerializer,
    AdminSummarySerializer,
    AdminWriteSerializer,
    PermissionAssignmentSerializer,
    PermissionSummarySerializer,
    RoleAssignmentSerializer,
    RoleSerializer,
    RoleSummarySerializer,
    RoleWriteSerializer,
)
from .services.auth_service import AuthService
from .services.management_service import AdminManagementError, UserManagementService
from .services.profile_service import AdminProfileService, ProfileServiceError


User = get_user_model()
management_service = UserManagementService()
profile_service = AdminProfileService()


class ManagementPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 10000


def paginate(queryset, request, view, serializer_class):
    paginator = ManagementPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    data = serializer_class(page, many=True).data
    return paginator.get_paginated_response(data).data


def raise_management_error(exc):
    raise ValidationError(exc.errors) from exc


def pop_assignments(actor, values):
    role_ids = values.pop("role_ids", None)
    permission_ids = values.pop("permission_ids", None)
    if role_ids is not None and not actor.has_perms(
        ("auth.change_permission", "auth.view_group")
    ):
        raise PermissionDenied(_("Role assignment access is required."))
    if permission_ids is not None and not actor.has_perms(
        ("auth.change_permission", "auth.view_permission")
    ):
        raise PermissionDenied(_("Permission assignment access is required."))
    return role_ids, permission_ids


def pop_role_assignments(actor, values):
    permission_ids = values.pop("permission_ids", None)
    admin_ids = values.pop("admin_ids", None)
    if permission_ids is not None and not actor.has_perms(
        ("auth.change_permission", "auth.view_permission")
    ):
        raise PermissionDenied(_("Permission assignment access is required."))
    if admin_ids is not None and not actor.has_perms(
        ("auth.change_permission", "auth.view_user")
    ):
        raise PermissionDenied(_("Admin assignment access is required."))
    return permission_ids, admin_ids


def get_admin(admin_id):
    try:
        return User.objects.prefetch_related(
            "groups", "user_permissions__content_type"
        ).get(pk=admin_id)
    except User.DoesNotExist as exc:
        raise NotFound(_("Admin not found.")) from exc


def get_role(role_id):
    try:
        return Group.objects.prefetch_related("permissions__content_type").get(pk=role_id)
    except Group.DoesNotExist as exc:
        raise NotFound(_("Role not found.")) from exc


class AdminLogin(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AuthService().authenticate_admin(
            serializer.validated_data["username"],
            serializer.validated_data["password"],
        )
        return api_response(True, "", result)


class AdminSelfProfile(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminPrincipalPermission]

    def get(self, request):
        user = profile_service.get_profile(request.user.pk)
        return api_response(True, "", AdminProfileSerializer(user).data)

    def patch(self, request):
        serializer = AdminProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        try:
            user = profile_service.update_profile(
                request.user.pk, serializer.validated_data
            )
        except ProfileServiceError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Profile updated."), AdminProfileSerializer(user).data)


class AdminSelfPassword(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminPrincipalPermission]

    def post(self, request):
        serializer = AdminPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile_service.change_password(
                request.user.pk,
                serializer.validated_data["current_password"],
                serializer.validated_data["new_password"],
            )
        except ProfileServiceError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Password changed."))


class UserPermissions(APIView):
    permission_classes = [AdminPrincipalPermission]

    def get(self, request):
        permissions = Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        grouped = {}
        for permission in permissions:
            grouped.setdefault(permission.content_type.app_label, []).append({
                "id": permission.id,
                "codename": permission.codename,
                "name": permission.name,
            })
        return api_response(True, "", {
            "permissions": grouped,
            "user_permissions": sorted(request.user.get_all_permissions()),
        })


class AdminListCreate(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_user",),
        "POST": ("auth.add_user",),
    }

    def get(self, request):
        admins = User.objects.filter(is_staff=True).prefetch_related(
            "groups", "user_permissions__content_type"
        )
        search = request.query_params.get("search", "").strip()
        if search:
            admins = admins.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        for field in ("is_active", "is_superuser"):
            value = request.query_params.get(field)
            if value in ("true", "false"):
                admins = admins.filter(**{field: value == "true"})
        role_id = request.query_params.get("role_id")
        if role_id:
            admins = admins.filter(groups__id=role_id)
        ordering = request.query_params.get("ordering", "username")
        allowed = {"id", "username", "email", "first_name", "last_name", "is_active", "date_joined"}
        if ordering.lstrip("-") not in allowed:
            ordering = "username"
        admins = admins.order_by(ordering, "id").distinct()
        return api_response(True, "", paginate(admins, request, self, AdminSerializer))

    def post(self, request):
        serializer = AdminWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        role_ids, permission_ids = pop_assignments(request.user, values)
        try:
            admin = management_service.create_admin(
                request.user, values, role_ids, permission_ids
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return api_response(
            True, _("Admin created."), AdminSerializer(admin).data, status_code=201
        )


class AdminDetail(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.change_user",),
        "PATCH": ("auth.change_user",),
    }

    def get(self, request, admin_id):
        return api_response(True, "", AdminSerializer(get_admin(admin_id)).data)

    def patch(self, request, admin_id):
        admin = get_admin(admin_id)
        serializer = AdminWriteSerializer(admin, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        role_ids, permission_ids = pop_assignments(request.user, values)
        try:
            admin = management_service.update_admin(
                request.user, admin, values, role_ids, permission_ids
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return api_response(True, _("Admin updated."), AdminSerializer(admin).data)


class AdminPasswordReset(APIView):
    permission_classes = [AdminPrincipalPermission, AdminSuperuserPermission]

    def post(self, request, admin_id):
        admin = get_admin(admin_id)
        serializer = AdminPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            management_service.reset_admin_password(
                request.user,
                admin,
                serializer.validated_data["current_password"],
                serializer.validated_data["new_password"],
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return api_response(True, _("Password changed."))


class AdminRoleAssignments(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_user", "auth.view_group"),
        "POST": (
            "auth.change_user", "auth.change_permission", "auth.view_user",
            "auth.view_group",
        ),
    }

    def get(self, request, admin_id):
        admin = get_admin(admin_id)
        return api_response(True, "", {
            "admin": AdminSummarySerializer(admin).data,
            "roles": RoleSummarySerializer(admin.groups.order_by("name"), many=True).data,
        })

    def post(self, request, admin_id):
        admin = get_admin(admin_id)
        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin = management_service.replace_admin_roles(
                request.user, admin, serializer.validated_data["role_ids"]
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return self.get(request, admin.pk)


class AdminPermissionAssignments(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_user", "auth.view_permission"),
        "POST": (
            "auth.change_user", "auth.change_permission", "auth.view_user",
            "auth.view_permission",
        ),
    }

    def get(self, request, admin_id):
        admin = get_admin(admin_id)
        permissions = admin.user_permissions.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        return api_response(True, "", {
            "admin": AdminSummarySerializer(admin).data,
            "permissions": PermissionSummarySerializer(permissions, many=True).data,
        })

    def post(self, request, admin_id):
        admin = get_admin(admin_id)
        serializer = PermissionAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin = management_service.replace_admin_permissions(
                request.user, admin, serializer.validated_data["permission_ids"]
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return self.get(request, admin.pk)


class RoleListCreate(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_group",),
        "POST": ("auth.add_group",),
    }

    def get(self, request):
        roles = Group.objects.annotate(
            admin_count=Count("user", distinct=True),
            permission_count=Count("permissions", distinct=True),
        ).prefetch_related("permissions__content_type")
        search = request.query_params.get("search", "").strip()
        if search:
            roles = roles.filter(name__icontains=search)
        permission_id = request.query_params.get("permission_id")
        if permission_id:
            roles = roles.filter(permissions__id=permission_id)
        ordering = request.query_params.get("ordering", "name")
        if ordering.lstrip("-") not in {"id", "name", "admin_count", "permission_count"}:
            ordering = "name"
        roles = roles.order_by(ordering, "id").distinct()
        return api_response(True, "", paginate(roles, request, self, RoleSerializer))

    def post(self, request):
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        permission_ids, admin_ids = pop_role_assignments(request.user, values)
        try:
            role = management_service.create_role(
                request.user, values, permission_ids, admin_ids
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        role.admin_count = role.user_set.filter(is_staff=True).count()
        return api_response(
            True, _("Role created."), RoleSerializer(role).data, status_code=201
        )


class RoleDetail(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_group",),
        "PATCH": ("auth.change_group",),
    }

    def get(self, request, role_id):
        role = get_role(role_id)
        role.admin_count = role.user_set.count()
        return api_response(True, "", RoleSerializer(role).data)

    def patch(self, request, role_id):
        role = get_role(role_id)
        serializer = RoleWriteSerializer(role, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        permission_ids, admin_ids = pop_role_assignments(request.user, values)
        try:
            role = management_service.update_role(
                request.user, role, values, permission_ids, admin_ids
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return api_response(True, _("Role updated."), self._serialize(role))

    @staticmethod
    def _serialize(role):
        role.admin_count = role.user_set.count()
        return RoleSerializer(role).data


class RolePermissionAssignments(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_group", "auth.view_permission"),
        "POST": (
            "auth.change_group", "auth.change_permission", "auth.view_group",
            "auth.view_permission",
        ),
    }

    def get(self, request, role_id):
        role = get_role(role_id)
        permissions = role.permissions.select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        return api_response(True, "", {
            "role": RoleSummarySerializer(role).data,
            "permissions": PermissionSummarySerializer(permissions, many=True).data,
        })

    def post(self, request, role_id):
        role = get_role(role_id)
        serializer = PermissionAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            management_service.replace_role_permissions(
                role, serializer.validated_data["permission_ids"]
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return self.get(request, role.pk)


class RoleAdminAssignments(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {
        "GET": ("auth.view_group", "auth.view_user"),
        "POST": (
            "auth.change_group", "auth.change_permission", "auth.view_group",
            "auth.view_user",
        ),
    }

    def get(self, request, role_id):
        role = get_role(role_id)
        admins = role.user_set.filter(is_staff=True).order_by("username", "id")
        return api_response(True, "", {
            "role": RoleSummarySerializer(role).data,
            "admins": AdminSummarySerializer(admins, many=True).data,
        })

    def post(self, request, role_id):
        role = get_role(role_id)
        serializer = AdminAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            management_service.replace_role_admins(
                request.user, role, serializer.validated_data["admin_ids"]
            )
        except AdminManagementError as exc:
            raise_management_error(exc)
        return self.get(request, role.pk)


def serialize_permission_catalog(permission):
    roles = permission.group_set.order_by("name", "id")
    direct_admins = permission.user_set.filter(is_staff=True).order_by("username", "id")
    inherited_admins = User.objects.filter(
        is_staff=True, groups__permissions=permission
    ).distinct().order_by("username", "id")
    inherited_data = []
    for admin in inherited_admins:
        source_roles = admin.groups.filter(permissions=permission).order_by("name", "id")
        item = AdminSummarySerializer(admin).data
        item["roles"] = RoleSummarySerializer(source_roles, many=True).data
        inherited_data.append(item)
    data = PermissionSummarySerializer(permission).data
    data["sources"] = {
        "roles": RoleSummarySerializer(roles, many=True).data,
        "direct_admins": AdminSummarySerializer(direct_admins, many=True).data,
        "inherited_admins": inherited_data,
    }
    return data


class PermissionCatalog(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {"GET": ("auth.view_permission",)}

    def get(self, request):
        permissions = Permission.objects.select_related("content_type").prefetch_related(
            "group_set", "user_set", "group_set__user_set"
        )
        search = request.query_params.get("search", "").strip()
        if search:
            permissions = permissions.filter(
                Q(codename__icontains=search)
                | Q(name__icontains=search)
                | Q(content_type__app_label__icontains=search)
                | Q(content_type__model__icontains=search)
            )
        app_label = request.query_params.get("app_label")
        if app_label:
            permissions = permissions.filter(content_type__app_label=app_label)
        model = request.query_params.get("model")
        if model:
            permissions = permissions.filter(content_type__model=model)
        role_id = request.query_params.get("role_id")
        if role_id:
            permissions = permissions.filter(group__id=role_id)
        admin_id = request.query_params.get("admin_id")
        if admin_id:
            permissions = permissions.filter(
                Q(user__id=admin_id) | Q(group__user__id=admin_id)
            )
        ordering = request.query_params.get("ordering", "content_type__app_label")
        allowed = {"id", "codename", "name", "content_type__app_label", "content_type__model"}
        if ordering.lstrip("-") not in allowed:
            ordering = "content_type__app_label"
        permissions = permissions.order_by(ordering, "codename", "id").distinct()
        paginator = ManagementPagination()
        page = paginator.paginate_queryset(permissions, request, view=self)
        data = [serialize_permission_catalog(permission) for permission in page]
        result = paginator.get_paginated_response(data).data
        return api_response(True, "", result)


class PermissionCatalogDetail(APIView):
    permission_classes = [AdminPrincipalPermission, AdminModelPermission]
    method_permissions = {"GET": ("auth.view_permission",)}

    def get(self, request, permission_id):
        try:
            permission = Permission.objects.select_related("content_type").get(
                pk=permission_id
            )
        except Permission.DoesNotExist as exc:
            raise NotFound(_("Permission not found.")) from exc
        return api_response(True, "", serialize_permission_catalog(permission))
