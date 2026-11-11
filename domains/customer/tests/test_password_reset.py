from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.customer.models import Customer, CustomerStatus


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class CustomerPasswordResetAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.inactive = CustomerStatus.objects.create(
            name="inactive", title="Inactive", is_active=False
        )
        unique = uuid.uuid4().int % 1_000_000_000
        self.customer = Customer.objects.create_user(
            id=unique,
            phone=f"09{unique:09d}",
            password="old-password",
            first_name="Reset",
            last_name="Customer",
            customer_code=f"CUS-RESET-{unique}",
            status=self.active,
        )
        self.inactive_customer = Customer.objects.create_user(
            id=unique + 1_000_000_000,
            phone=f"08{unique:09d}",
            password="old-password",
            first_name="Inactive",
            last_name="Customer",
            customer_code=f"CUS-INACTIVE-{unique}",
            status=self.inactive,
        )
        self.sms_patcher = patch(
            "domains.customer.services.auth_service.SMSService.send",
            return_value=SimpleNamespace(status="pending"),
        )
        self.sms_send = self.sms_patcher.start()
        self.addCleanup(self.sms_patcher.stop)
        self.delivery_patcher = patch(
            "domains.customer.tasks.deliver_password_reset_sms.apply_async"
        )
        self.delivery_task = self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)

    def request_reset(self, phone=None):
        return self.client.post(
            "/api/customer/password/forgot",
            {"phone": phone or self.customer.phone},
            format="json",
        )

    def confirm_reset(self, request_id, **overrides):
        payload = {
            "request_id": request_id,
            "code": "123456",
            "new_password": "StrongReset!8374",
            "new_password_confirmation": "StrongReset!8374",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/customer/password/forgot/confirmation",
            payload,
            format="json",
        )

    def test_existing_unknown_and_inactive_requests_have_same_public_shape(self):
        existing = self.request_reset()
        unknown = self.request_reset("09111111111")
        inactive = self.request_reset(self.inactive_customer.phone)

        self.assertEqual(existing.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(inactive.status_code, 202)
        self.assertEqual(set(existing.data["data"]), set(unknown.data["data"]))
        self.assertEqual(set(existing.data["data"]), set(inactive.data["data"]))
        self.assertEqual(existing.data["message"], unknown.data["message"])
        self.assertEqual(existing.data["message"], inactive.data["message"])
        self.assertEqual(self.delivery_task.call_count, 3)
        queued_ids = [call.kwargs["args"][0] for call in self.delivery_task.call_args_list]
        self.assertEqual(queued_ids, [self.customer.pk, None, None])

    def test_unknown_account_challenge_cannot_reset_password(self):
        requested = self.request_reset("09111111112")

        response = self.confirm_reset(requested.data["data"]["request_id"])

        self.assertEqual(response.status_code, 400)

    def test_reset_changes_password_verifies_phone_and_prevents_replay(self):
        requested = self.request_reset()
        request_id = requested.data["data"]["request_id"]

        response = self.confirm_reset(request_id)

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("StrongReset!8374"))
        self.assertIsNotNone(self.customer.phone_verified_at)
        self.assertEqual(self.confirm_reset(request_id).status_code, 400)

    def test_password_validation_does_not_consume_code(self):
        requested = self.request_reset()
        request_id = requested.data["data"]["request_id"]

        weak = self.confirm_reset(
            request_id,
            new_password="12345678",
            new_password_confirmation="12345678",
        )
        valid = self.confirm_reset(request_id)

        self.assertEqual(weak.status_code, 400)
        self.assertEqual(valid.status_code, 200)

    def test_account_similarity_validation_does_not_consume_code(self):
        requested = self.request_reset()
        request_id = requested.data["data"]["request_id"]

        similar = self.confirm_reset(
            request_id,
            new_password="Reset123!",
            new_password_confirmation="Reset123!",
        )
        valid = self.confirm_reset(request_id)

        self.assertEqual(similar.status_code, 400)
        self.assertEqual(valid.status_code, 200)

    def test_password_change_invalidates_pending_reset(self):
        requested = self.request_reset()
        self.customer.set_password("changed-elsewhere")
        self.customer.save(update_fields=["password"])

        response = self.confirm_reset(requested.data["data"]["request_id"])

        self.assertEqual(response.status_code, 400)

    def test_old_customer_access_token_is_rejected_after_reset(self):
        refresh = RefreshToken.for_user(self.customer)
        refresh["user_type"] = "customer"
        old_access = str(refresh.access_token)
        requested = self.request_reset()
        self.assertEqual(
            self.confirm_reset(requested.data["data"]["request_id"]).status_code,
            200,
        )

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
        response = self.client.get("/api/customer/me")

        self.assertEqual(response.status_code, 401)

    def test_persian_phone_digits_find_canonical_customer(self):
        translation = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

        response = self.request_reset(self.customer.phone.translate(translation))

        self.assertEqual(response.status_code, 202)
        self.delivery_task.assert_called_once()

    def test_delivery_task_sends_sensitive_expiring_sms_for_eligible_customer(self):
        expires_at = timezone.now() + timedelta(minutes=2)

        from domains.customer.tasks import deliver_password_reset_sms

        deliver_password_reset_sms(
            self.customer.pk,
            "123456",
            expires_at.isoformat(),
        )

        self.sms_send.assert_called_once()
        values = self.sms_send.call_args.kwargs
        self.assertEqual(values["receiver"], self.customer.phone)
        self.assertTrue(values["sensitive"])
        self.assertEqual(values["expires_at"], expires_at)
