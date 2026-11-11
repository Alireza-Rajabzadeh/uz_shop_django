from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.customer.models import Customer, CustomerStatus


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class CustomerPhoneConfirmationAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        unique = uuid.uuid4().int % 1_000_000_000
        self.customer = Customer.objects.create_user(
            id=unique,
            phone=f"09{unique:09d}",
            password="password",
            first_name="Verify",
            last_name="Phone",
            customer_code=f"CUS-VERIFY-{unique}",
            status=self.active,
        )
        self.client.force_authenticate(self.customer)
        self.sms_patcher = patch(
            "domains.customer.services.auth_service.SMSService.send",
            return_value=SimpleNamespace(status="pending"),
        )
        self.sms_send = self.sms_patcher.start()
        self.addCleanup(self.sms_patcher.stop)

    def request_confirmation(self):
        return self.client.post("/api/customer/me/phone/confirmation", {}, format="json")

    def test_request_and_confirm_marks_phone_verified(self):
        requested = self.request_confirmation()

        self.assertEqual(requested.status_code, 202)
        self.assertNotIn(self.customer.phone, requested.data["data"]["destination"])
        values = self.sms_send.call_args.kwargs
        self.assertEqual(values["receiver"], self.customer.phone)
        self.assertTrue(values["sensitive"])
        self.assertIsNotNone(values["expires_at"])

        confirmed = self.client.post(
            "/api/customer/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertIsNotNone(confirmed.data["data"]["phone_verified_at"])
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.phone_verified_at)
        replay = self.client.post(
            "/api/customer/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )
        self.assertEqual(replay.status_code, 400)

    def test_already_verified_phone_cannot_request_another_code(self):
        self.customer.phone_verified_at = timezone.now()
        self.customer.save(update_fields=["phone_verified_at"])

        response = self.request_confirmation()

        self.assertEqual(response.status_code, 400)
        self.sms_send.assert_not_called()

    def test_confirmation_is_bound_to_authenticated_customer(self):
        requested = self.request_confirmation()
        other = Customer.objects.create_user(
            phone="09128888888",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code=f"CUS-VERIFY-OTHER-{self.customer.pk}",
            status=self.active,
        )
        self.client.force_authenticate(other)

        response = self.client.post(
            "/api/customer/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertIsNone(other.phone_verified_at)

        self.client.force_authenticate(self.customer)
        original = self.client.post(
            "/api/customer/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )
        self.assertEqual(original.status_code, 200)

    def test_phone_confirmation_rejects_unauthenticated_and_admin_tokens(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.request_confirmation().status_code, 401)

        admin = User.objects.create_user(
            username=f"phone-admin-{self.customer.pk}",
            password="password",
            is_staff=True,
        )
        refresh = RefreshToken.for_user(admin)
        refresh["user_type"] = "admin"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        self.assertEqual(self.request_confirmation().status_code, 401)
