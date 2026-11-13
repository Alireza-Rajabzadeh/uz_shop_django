from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.customer.models import Customer, CustomerStatus


User = get_user_model()


class UserManagementAPITests(APITestCase):
    password = "StrongTest123!"

    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser(
            username="root", email="root@example.com", password=cls.password
        )
        cls.staff = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password=cls.password,
            is_staff=True,
        )
        cls.target = User.objects.create_user(
            username="target",
            email="target@example.com",
            password=cls.password,
            is_staff=True,
        )
        cls.view_user = Permission.objects.get(
            content_type__app_label="auth", codename="view_user"
        )
        cls.change_user = Permission.objects.get(
            content_type__app_label="auth", codename="change_user"
        )
        cls.view_group = Permission.objects.get(
            content_type__app_label="auth", codename="view_group"
        )
        cls.change_group = Permission.objects.get(
            content_type__app_label="auth", codename="change_group"
        )
        cls.view_permission = Permission.objects.get(
            content_type__app_label="auth", codename="view_permission"
        )

    def authenticate(self, user=None):
        user = user or self.superadmin
        refresh = RefreshToken.for_user(user)
        refresh["user_type"] = "admin"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def assertEnvelope(self, response, success=True):
        self.assertEqual(response.data["success"], success)
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)
        self.assertIn("errors", response.data)

    def test_login_and_admin_only_bootstrap_are_retained(self):
        role = Group.objects.create(name="login-role")
        self.superadmin.groups.add(role)
        response = self.client.post(
            "/api/users/login",
            {"username": self.superadmin.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEnvelope(response)
        profile = response.data["data"]["user"]
        self.assertEqual(profile["id"], self.superadmin.id)
        self.assertEqual(profile["roles"], [{"id": role.id, "name": role.name}])
        self.assertIn("auth.view_user", profile["effective_permissions"])

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['data']['access']}"
        )
        response = self.client.get("/api/users/permissions")
        self.assertEqual(response.status_code, 200)
        self.assertIn("permissions", response.data["data"])
        self.assertIn("auth.view_user", response.data["data"]["user_permissions"])

    def test_self_profile_returns_current_roles_and_permissions(self):
        role = Group.objects.create(name="profile-role")
        role.permissions.add(self.view_user)
        self.staff.groups.add(role)
        self.authenticate(self.staff)

        response = self.client.get("/api/users/me")

        self.assertEqual(response.status_code, 200)
        self.assertEnvelope(response)
        profile = response.data["data"]
        self.assertEqual(profile["id"], self.staff.id)
        self.assertEqual(profile["roles"], [{"id": role.id, "name": role.name}])
        self.assertIn("auth.view_user", profile["effective_permissions"])

    def test_self_profile_update_requires_password_for_sensitive_fields(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            "/api/users/me", {"first_name": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["first_name"], "Updated")

        response = self.client.patch(
            "/api/users/me", {"email": "changed@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            "/api/users/me",
            {"email": "changed@example.com", "current_password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["email"], "changed@example.com")

        response = self.client.patch(
            "/api/users/me", {"is_superuser": True}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_self_password_change_validates_and_updates_password(self):
        self.authenticate(self.staff)
        new_password = "AnotherStrong456!"

        response = self.client.post(
            "/api/users/me/password",
            {
                "current_password": "wrong-password",
                "new_password": new_password,
                "new_password_confirmation": new_password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/users/me/password",
            {
                "current_password": self.password,
                "new_password": new_password,
                "new_password_confirmation": new_password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEnvelope(response)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password(new_password))

    def test_superuser_can_reset_another_admin_password(self):
        target_refresh = RefreshToken.for_user(self.target)
        target_refresh["user_type"] = "admin"
        old_access = str(target_refresh.access_token)
        new_password = "ResetStrong456!"
        self.authenticate()

        response = self.client.post(
            f"/api/users/admins/{self.target.id}/password",
            {
                "current_password": self.password,
                "new_password": new_password,
                "new_password_confirmation": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEnvelope(response)
        self.assertIsNone(response.data["data"])
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(new_password))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_non_superuser_cannot_reset_admin_password(self):
        self.staff.user_permissions.add(self.change_user)
        old_hash = self.target.password
        self.authenticate(self.staff)

        response = self.client.post(
            f"/api/users/admins/{self.target.id}/password",
            {
                "current_password": self.password,
                "new_password": "ResetStrong456!",
                "new_password_confirmation": "ResetStrong456!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.password, old_hash)

    def test_superuser_password_reset_rejects_self_and_wrong_password(self):
        self.authenticate()
        payload = {
            "current_password": self.password,
            "new_password": "ResetStrong456!",
            "new_password_confirmation": "ResetStrong456!",
        }
        response = self.client.post(
            f"/api/users/admins/{self.superadmin.id}/password", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)

        payload["current_password"] = "wrong-password"
        response = self.client.post(
            f"/api/users/admins/{self.target.id}/password", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.target.check_password(self.password))

    def test_generic_admin_patch_cannot_change_password(self):
        old_hash = self.target.password
        self.authenticate()

        response = self.client.patch(
            f"/api/users/admins/{self.target.id}",
            {"password": "ResetStrong456!"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.target.refresh_from_db()
        self.assertEqual(self.target.password, old_hash)

    def test_customer_token_cannot_access_admin_endpoints_or_bootstrap(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="09120000000",
            password=self.password,
            first_name="Customer",
            last_name="Only",
            status=status,
        )
        refresh = RefreshToken.for_user(customer)
        refresh["user_type"] = "customer"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get("/api/users/me")
        self.assertEqual(response.status_code, 401)
        self.assertEnvelope(response, success=False)

        for url in ("/api/users/permissions", "/api/users/admins", "/api/users/roles"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertEnvelope(response, success=False)

    def test_admin_authentication_rechecks_active_and_staff_after_token_issue(self):
        self.authenticate(self.staff)
        User.objects.filter(pk=self.staff.pk).update(is_staff=False)
        response = self.client.get("/api/users/permissions")
        self.assertEqual(response.status_code, 401)

        User.objects.filter(pk=self.staff.pk).update(is_staff=True, is_active=False)
        response = self.client.get("/api/users/permissions")
        self.assertEqual(response.status_code, 401)

    def test_model_permissions_are_required(self):
        self.authenticate(self.staff)
        response = self.client.get("/api/users/admins")
        self.assertEqual(response.status_code, 403)

        self.staff.user_permissions.add(self.view_user)
        response = self.client.get("/api/users/admins")
        self.assertEqual(response.status_code, 200)
        self.assertEnvelope(response)

        response = self.client.post(
            f"/api/users/admins/{self.target.id}/role-assignments",
            {"role_ids": []},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_create_hashes_password_and_patch_does_not_clear_it(self):
        self.authenticate()
        response = self.client.post(
            "/api/users/admins",
            {
                "username": "created-admin",
                "email": "created@example.com",
                "password": self.password,
                "first_name": "Created",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        admin = User.objects.get(pk=response.data["data"]["id"])
        self.assertTrue(admin.is_staff)
        self.assertNotEqual(admin.password, self.password)
        self.assertTrue(admin.check_password(self.password))

        old_hash = admin.password
        response = self.client.patch(
            f"/api/users/admins/{admin.id}", {"first_name": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertEqual(admin.password, old_hash)

    def test_lists_use_enveloped_drf_pagination_and_support_filters(self):
        self.authenticate()
        response = self.client.get("/api/users/admins?search=target&is_staff=true")
        self.assertEqual(response.status_code, 200)
        page = response.data["data"]
        self.assertEqual(set(page), {"count", "next", "previous", "results"})
        self.assertEqual([item["username"] for item in page["results"]], ["target"])

        response = self.client.get("/api/users/roles?search=missing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 0)

        response = self.client.get("/api/users/permission-catalog?app_label=auth")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["data"]["count"], 0)

    def test_admin_role_and_direct_permission_replacements(self):
        self.authenticate()
        first = Group.objects.create(name="first-role")
        second = Group.objects.create(name="second-role")
        self.target.groups.add(first)
        self.target.user_permissions.add(self.view_user)

        response = self.client.post(
            f"/api/users/admins/{self.target.id}/role-assignments",
            {"role_ids": [second.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.target.groups.values_list("id", flat=True)), [second.id])

        response = self.client.post(
            f"/api/users/admins/{self.target.id}/permission-assignments",
            {"permission_ids": [self.change_user.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(self.target.user_permissions.values_list("id", flat=True)),
            [self.change_user.id],
        )

    def test_change_user_alone_cannot_escalate_through_assignments(self):
        self.staff.user_permissions.add(self.view_user, self.change_user, self.view_permission)
        self.authenticate(self.staff)
        response = self.client.post(
            f"/api/users/admins/{self.staff.id}/permission-assignments",
            {"permission_ids": [self.change_group.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.staff.user_permissions.filter(pk=self.change_group.id).exists())

    def test_admin_create_with_assignments_is_atomic(self):
        self.authenticate()
        role = Group.objects.create(name="created-role")
        response = self.client.post(
            "/api/users/admins",
            {
                "username": "aggregate-admin",
                "email": "aggregate@example.com",
                "password": self.password,
                "role_ids": [role.id],
                "permission_ids": [self.view_user.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        admin = User.objects.get(username="aggregate-admin")
        self.assertEqual(list(admin.groups.values_list("id", flat=True)), [role.id])
        self.assertEqual(
            list(admin.user_permissions.values_list("id", flat=True)),
            [self.view_user.id],
        )

        response = self.client.post(
            "/api/users/admins",
            {
                "username": "invalid-aggregate",
                "email": "invalid@example.com",
                "password": self.password,
                "role_ids": [999999],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="invalid-aggregate").exists())

    def test_role_permission_and_admin_replacements(self):
        self.authenticate()
        role = Group.objects.create(name="managed-role")
        response = self.client.post(
            f"/api/users/roles/{role.id}/permission-assignments",
            {"permission_ids": [self.view_user.id, self.change_user.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(role.permissions.count(), 2)

        response = self.client.post(
            f"/api/users/roles/{role.id}/admin-assignments",
            {"admin_ids": [self.target.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(role.user_set.values_list("id", flat=True)), [self.target.id])

    def test_role_create_with_assignments_is_atomic(self):
        self.authenticate()
        response = self.client.post(
            "/api/users/roles",
            {
                "name": "aggregate-role",
                "permission_ids": [self.view_user.id],
                "admin_ids": [self.target.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        role = Group.objects.get(name="aggregate-role")
        self.assertEqual(list(role.permissions.values_list("id", flat=True)), [self.view_user.id])
        self.assertEqual(list(role.user_set.values_list("id", flat=True)), [self.target.id])

        response = self.client.post(
            "/api/users/roles",
            {"name": "invalid-role", "permission_ids": [999999]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Group.objects.filter(name="invalid-role").exists())

    def test_invalid_replacement_is_atomic(self):
        self.authenticate()
        role = Group.objects.create(name="atomic-role")
        self.target.groups.add(role)
        response = self.client.post(
            f"/api/users/admins/{self.target.id}/role-assignments",
            {"role_ids": [999999]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.target.groups.values_list("id", flat=True)), [role.id])

    def test_permission_catalog_reports_role_direct_and_inherited_sources(self):
        self.authenticate()
        role = Group.objects.create(name="source-role")
        role.permissions.add(self.view_user)
        inherited = User.objects.create_user(
            username="inherited", password=self.password, is_staff=True
        )
        inherited.groups.add(role)
        self.target.user_permissions.add(self.view_user)

        response = self.client.get(
            f"/api/users/permission-catalog/{self.view_user.id}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["app_label"], "auth")
        self.assertEqual(data["model"], "user")
        self.assertEqual(data["full_codename"], "auth.view_user")
        self.assertIn(role.id, [item["id"] for item in data["sources"]["roles"]])
        self.assertIn(
            self.target.id,
            [item["id"] for item in data["sources"]["direct_admins"]],
        )
        inherited_source = next(
            item
            for item in data["sources"]["inherited_admins"]
            if item["id"] == inherited.id
        )
        self.assertEqual(inherited_source["roles"][0]["id"], role.id)

    def test_non_superuser_cannot_create_or_edit_superusers(self):
        self.staff.user_permissions.add(self.change_user)
        self.authenticate(self.staff)
        response = self.client.patch(
            f"/api/users/admins/{self.target.id}",
            {"is_superuser": True},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            f"/api/users/admins/{self.superadmin.id}",
            {"first_name": "Forbidden"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_self_lockout_and_last_superuser_safety(self):
        self.authenticate()
        for payload in ({"is_active": False}, {"is_staff": False}):
            response = self.client.patch(
                f"/api/users/admins/{self.superadmin.id}", payload, format="json"
            )
            self.assertEqual(response.status_code, 400)

        # The final active staff superuser cannot be changed even by that superuser.
        other = User.objects.create_superuser(
            username="other-root", password=self.password, email="other@example.com"
        )
        self.authenticate(other)
        response = self.client.patch(
            f"/api/users/admins/{self.superadmin.id}",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(
            f"/api/users/admins/{other.id}",
            {"is_superuser": False},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
