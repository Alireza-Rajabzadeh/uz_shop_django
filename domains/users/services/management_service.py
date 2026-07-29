from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _


User = get_user_model()


class AdminManagementError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class UserManagementService:
    @staticmethod
    def _validate_superuser_change(actor, admin, values):
        if not actor.is_superuser and (
            admin.is_superuser or values.get("is_superuser", admin.is_superuser)
        ):
            raise AdminManagementError(
                {"is_superuser": "Only a superuser can create or edit a superuser."}
            )

        resulting_active = values.get("is_active", admin.is_active)
        resulting_staff = values.get("is_staff", admin.is_staff)
        resulting_superuser = values.get("is_superuser", admin.is_superuser)
        if admin.pk == actor.pk and (not resulting_active or not resulting_staff):
            raise AdminManagementError(
                {"admin": "You cannot deactivate your own account or remove your staff status."}
            )

        if (
            admin.is_active
            and admin.is_staff
            and admin.is_superuser
            and not (resulting_active and resulting_staff and resulting_superuser)
        ):
            other_superusers = User.objects.select_for_update().filter(
                is_active=True, is_staff=True, is_superuser=True
            ).exclude(pk=admin.pk)
            if not other_superusers.exists():
                raise AdminManagementError(
                    {"admin": "The last active staff superuser cannot be demoted or disabled."}
                )

    @transaction.atomic
    def create_admin(self, actor, values, role_ids=None, permission_ids=None):
        roles = self._objects_for_ids(Group, role_ids or [], "role_ids")
        permissions = self._objects_for_ids(
            Permission, permission_ids or [], "permission_ids"
        )
        candidate = User(is_staff=values.get("is_staff", True))
        self._validate_superuser_change(actor, candidate, values)
        password = values.pop("password")
        admin = User(**values)
        if "is_staff" not in values:
            admin.is_staff = True
        admin.set_password(password)
        admin.full_clean(exclude=("password",))
        admin.save()
        admin.groups.set(roles)
        admin.user_permissions.set(permissions)
        return admin

    @transaction.atomic
    def update_admin(self, actor, admin, values, role_ids=None, permission_ids=None):
        admin = User.objects.select_for_update().get(pk=admin.pk)
        if "password" in values:
            raise AdminManagementError({
                "password": _("Use the administrator password reset endpoint.")
            })
        self._validate_superuser_change(actor, admin, values)
        for field, value in values.items():
            setattr(admin, field, value)
        admin.full_clean(exclude=("password",))
        admin.save()
        if role_ids is not None:
            admin.groups.set(self._objects_for_ids(Group, role_ids, "role_ids"))
        if permission_ids is not None:
            admin.user_permissions.set(
                self._objects_for_ids(Permission, permission_ids, "permission_ids")
            )
        return admin

    @transaction.atomic
    def reset_admin_password(self, actor, admin, current_password, new_password):
        actor = User.objects.select_for_update().get(pk=actor.pk)
        admin = User.objects.select_for_update().get(pk=admin.pk)
        if not actor.is_superuser:
            raise AdminManagementError({"admin": _("Only a superuser can reset administrator passwords.")})
        if actor.pk == admin.pk:
            raise AdminManagementError({"admin": _("Use your profile to change your own password.")})
        if not admin.is_staff:
            raise AdminManagementError({"admin": _("Administrator not found.")})
        if not actor.check_password(current_password):
            raise AdminManagementError({"current_password": _("The current password is incorrect.")})
        try:
            password_validation.validate_password(new_password, user=admin)
        except ValidationError as exc:
            raise AdminManagementError({"new_password": exc.messages}) from exc
        admin.set_password(new_password)
        admin.save(update_fields=("password",))

    @staticmethod
    def _objects_for_ids(model, ids, field):
        unique_ids = list(dict.fromkeys(ids))
        objects = list(model.objects.filter(pk__in=unique_ids))
        found = {obj.pk for obj in objects}
        missing = [pk for pk in unique_ids if pk not in found]
        if missing:
            raise AdminManagementError({field: f"Unknown IDs: {missing}."})
        return objects

    @staticmethod
    def _validate_role_admins(actor, admins, current_ids=None):
        non_staff = [admin.pk for admin in admins if not admin.is_staff]
        if non_staff:
            raise AdminManagementError({"admin_ids": f"Users are not staff: {non_staff}."})
        requested_ids = {admin.pk for admin in admins}
        changed_ids = requested_ids.symmetric_difference(current_ids or set())
        if User.objects.filter(pk__in=changed_ids, is_superuser=True).exists() and not actor.is_superuser:
            raise AdminManagementError(
                {"admin_ids": "Only a superuser can change a superuser's roles."}
            )

    @transaction.atomic
    def create_role(self, actor, values, permission_ids=None, admin_ids=None):
        permissions = self._objects_for_ids(
            Permission, permission_ids or [], "permission_ids"
        )
        admins = self._objects_for_ids(User, admin_ids or [], "admin_ids")
        self._validate_role_admins(actor, admins)
        role = Group.objects.create(**values)
        role.permissions.set(permissions)
        role.user_set.set(admins)
        return role

    @transaction.atomic
    def update_role(self, actor, role, values, permission_ids=None, admin_ids=None):
        role = Group.objects.select_for_update().get(pk=role.pk)
        if "name" in values:
            role.name = values["name"]
            role.full_clean()
            role.save(update_fields=["name"])
        if permission_ids is not None:
            role.permissions.set(
                self._objects_for_ids(Permission, permission_ids, "permission_ids")
            )
        if admin_ids is not None:
            admins = self._objects_for_ids(User, admin_ids, "admin_ids")
            current_ids = set(role.user_set.values_list("pk", flat=True))
            self._validate_role_admins(actor, admins, current_ids)
            role.user_set.set(admins)
        return role

    @transaction.atomic
    def replace_admin_roles(self, actor, admin, role_ids):
        admin = User.objects.select_for_update().get(pk=admin.pk)
        if admin.is_superuser and not actor.is_superuser:
            raise AdminManagementError({"admin": "Only a superuser can edit a superuser."})
        roles = self._objects_for_ids(Group, role_ids, "role_ids")
        admin.groups.set(roles)
        return admin

    @transaction.atomic
    def replace_admin_permissions(self, actor, admin, permission_ids):
        admin = User.objects.select_for_update().get(pk=admin.pk)
        if admin.is_superuser and not actor.is_superuser:
            raise AdminManagementError({"admin": "Only a superuser can edit a superuser."})
        permissions = self._objects_for_ids(Permission, permission_ids, "permission_ids")
        admin.user_permissions.set(permissions)
        return admin

    @transaction.atomic
    def replace_role_permissions(self, role, permission_ids):
        role = Group.objects.select_for_update().get(pk=role.pk)
        permissions = self._objects_for_ids(Permission, permission_ids, "permission_ids")
        role.permissions.set(permissions)
        return role

    @transaction.atomic
    def replace_role_admins(self, actor, role, admin_ids):
        role = Group.objects.select_for_update().get(pk=role.pk)
        admins = self._objects_for_ids(User, admin_ids, "admin_ids")
        current_ids = set(role.user_set.values_list("pk", flat=True))
        self._validate_role_admins(actor, admins, current_ids)
        role.user_set.set(admins)
        return role
