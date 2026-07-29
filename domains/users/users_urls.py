from django.urls import path

from .views import (
    AdminDetail,
    AdminListCreate,
    AdminLogin,
    AdminPasswordReset,
    AdminPermissionAssignments,
    AdminRoleAssignments,
    AdminSelfPassword,
    AdminSelfProfile,
    PermissionCatalog,
    PermissionCatalogDetail,
    RoleAdminAssignments,
    RoleDetail,
    RoleListCreate,
    RolePermissionAssignments,
    UserPermissions,
)


urlpatterns = [
    path("login", AdminLogin.as_view()),
    path("me", AdminSelfProfile.as_view()),
    path("me/password", AdminSelfPassword.as_view()),
    path("permissions", UserPermissions.as_view()),
    path("admins", AdminListCreate.as_view()),
    path("admins/<int:admin_id>", AdminDetail.as_view()),
    path("admins/<int:admin_id>/password", AdminPasswordReset.as_view()),
    path("admins/<int:admin_id>/role-assignments", AdminRoleAssignments.as_view()),
    path(
        "admins/<int:admin_id>/permission-assignments",
        AdminPermissionAssignments.as_view(),
    ),
    path("roles", RoleListCreate.as_view()),
    path("roles/<int:role_id>", RoleDetail.as_view()),
    path(
        "roles/<int:role_id>/permission-assignments",
        RolePermissionAssignments.as_view(),
    ),
    path("roles/<int:role_id>/admin-assignments", RoleAdminAssignments.as_view()),
    path("permission-catalog", PermissionCatalog.as_view()),
    path("permission-catalog/<int:permission_id>", PermissionCatalogDetail.as_view()),
]
