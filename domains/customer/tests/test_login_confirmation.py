from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.test import override_settings
from rest_framework.test import APITestCase

from core.services import ConfirmedRequestService
from domains.customer.models import Customer, CustomerStatus
from domains.notifications.services import NotificationError


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class CustomerLoginConfirmationAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        unique = uuid.uuid4().int % 1_000_000_000
        self.customer = Customer.objects.create_user(
            id=unique,
            phone=f"09{unique:09d}",
            password="password",
            first_name="Login",
            last_name="Customer",
            customer_code=f"CUS-{unique}",
            status=self.active,
        )
        self.sms_patcher = patch(
            "domains.customer.services.auth_service.SMSService.send",
            return_value=SimpleNamespace(status="pending"),
        )
        self.sms_send = self.sms_patcher.start()
        self.addCleanup(self.sms_patcher.stop)

    def request_confirmation(self):
        return self.client.post(
            "/api/customer/login",
            {"phone": self.customer.phone, "password": "password"},
            format="json",
        )

    def test_login_requires_confirmation_before_issuing_tokens(self):
        response = self.request_confirmation()

        self.assertEqual(response.status_code, 202)
        self.assertNotIn("access", response.data["data"])
        self.assertGreater(response.data["data"]["expires_in"], 0)
        self.assertLessEqual(response.data["data"]["expires_in"], 120)
        self.assertGreater(response.data["data"]["resend_after"], 0)
        self.assertLessEqual(response.data["data"]["resend_after"], 30)
        self.assertNotIn(self.customer.phone, response.data["data"]["destination"])
        request_key = ConfirmedRequestService._request_key(
            response.data["data"]["request_id"]
        )
        cached = ConfirmedRequestService().connection.get(request_key)
        self.assertNotIn(b"password", cached)
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.last_login)
        sent_message = self.sms_send.call_args.kwargs["message"]
        self.assertIn("123456", sent_message)
        self.assertNotIn("password", sent_message)

    def test_confirmation_issues_tokens_and_is_one_time(self):
        requested = self.request_confirmation()
        payload = {
            "request_id": requested.data["data"]["request_id"],
            "code": "123456",
        }

        confirmed = self.client.post(
            "/api/customer/login/confirmation", payload, format="json"
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertIn("access", confirmed.data["data"])
        self.assertIn("refresh", confirmed.data["data"])
        self.customer.refresh_from_db()
        self.assertIsNotNone(self.customer.last_login)
        replay = self.client.post(
            "/api/customer/login/confirmation", payload, format="json"
        )
        self.assertEqual(replay.status_code, 400)

    def test_wrong_code_is_rejected(self):
        requested = self.request_confirmation()

        response = self.client.post(
            "/api/customer/login/confirmation",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.last_login)

    def test_password_change_invalidates_pending_confirmation(self):
        requested = self.request_confirmation()
        self.customer.set_password("new-password")
        self.customer.save(update_fields=["password"])

        response = self.client.post(
            "/api/customer/login/confirmation",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_repeated_login_is_throttled(self):
        self.assertEqual(self.request_confirmation().status_code, 202)
        response = self.request_confirmation()
        self.assertEqual(response.status_code, 429)

    def test_sms_queue_failure_removes_challenge_and_cooldown(self):
        self.sms_send.side_effect = [
            NotificationError({"detail": ["queue unavailable"]}),
            SimpleNamespace(status="pending"),
        ]

        failed = self.request_confirmation()
        retried = self.request_confirmation()

        self.assertEqual(failed.status_code, 503)
        self.assertEqual(retried.status_code, 202)
