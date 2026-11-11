from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.customer.models import Customer, CustomerStatus


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class CustomerChangePasswordAPITests(APITestCase):
    def setUp(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09123333333", password="old-password", first_name="Change",
            last_name="Password", customer_code="CUS-30001", status=status,
        )
        refresh = RefreshToken.for_user(self.customer)
        refresh["user_type"] = "customer"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def url(self):
        return f"/api/customer/me/password"

    def payload(self, **overrides):
        data = {
            "current_password": "old-password",
            "new_password": "new-password-123",
            "new_password_confirmation": "new-password-123",
        }
        data.update(overrides)
        return data

    def test_change_password_requires_authentication(self):
        self.client.credentials()
        response = self.client.post(self.url(), self.payload(), format="json")
        self.assertEqual(response.status_code, 401)

    def test_change_password_success(self):
        response = self.client.post(self.url(), self.payload(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.check_password("old-password"))
        self.assertTrue(self.customer.check_password("new-password-123"))

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(
            self.url(), self.payload(current_password="wrong-password"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.data["errors"])
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("old-password"))

    def test_change_password_rejects_mismatched_confirmation(self):
        response = self.client.post(
            self.url(), self.payload(new_password_confirmation="different"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password_confirmation", response.data["errors"])
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("old-password"))

    def test_change_password_rejects_weak_password(self):
        response = self.client.post(
            self.url(), self.payload(new_password="123456", new_password_confirmation="123456"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data["errors"])
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("old-password"))
