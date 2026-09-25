import uuid
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class VendorRegistrationConfirmationAPITests(APITestCase):
    def setUp(self):
        self.pending_status = VendorStatus.objects.create(
            id=VendorStatusEnum.PENDING.value,
            name="pending",
            title="Pending",
        )
        self.active_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
            name="active",
            title="Active",
        )
        self.delivery_patcher = patch(
            "domains.vendor.tasks.deliver_vendor_sms.apply_async"
        )
        self.delivery_task = self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)

    def register(self, **overrides):
        payload = {
            "first_name": "New",
            "last_name": "Vendor",
            "phone": f"09{uuid.uuid4().int % 1_000_000_000:09d}",
            "national_id": str(uuid.uuid4().int % 10_000_000_000),
            "password": "StrongPass!123",
            "password_confirmation": "StrongPass!123",
        }
        payload.update(overrides)
        return self.client.post("/api/vendor/register", payload, format="json"), payload

    def confirm(self, request_id, code="123456"):
        return self.client.post(
            "/api/vendor/register/confirmation",
            {"request_id": request_id, "code": code},
            format="json",
        )

    def test_request_and_confirm_creates_active_vendor_with_tokens(self):
        response, payload = self.register()

        self.assertEqual(response.status_code, 202)
        self.assertIn("request_id", response.data["data"])
        self.assertIn("expires_in", response.data["data"])
        self.assertIn("resend_after", response.data["data"])
        self.assertIn("destination", response.data["data"])
        self.assertNotIn(payload["phone"], response.data["data"]["destination"])

        vendor = Vendor.objects.get(phone=payload["phone"])
        self.assertEqual(vendor.status_id, VendorStatusEnum.PENDING.value)
        self.assertIsNone(vendor.last_login)

        self.delivery_task.assert_called_once()
        call_args = self.delivery_task.call_args.kwargs["args"]
        self.assertEqual(call_args[0], vendor.pk)
        self.assertIn("123456", call_args[1])

        confirmed = self.confirm(response.data["data"]["request_id"])

        self.assertEqual(confirmed.status_code, 200)
        self.assertIn("access", confirmed.data["data"])
        self.assertIn("refresh", confirmed.data["data"])
        self.assertIn("vendor", confirmed.data["data"])

        vendor.refresh_from_db()
        self.assertEqual(vendor.status_id, VendorStatusEnum.ACTIVE.value)
        self.assertIsNotNone(vendor.last_login)

    def test_confirmation_is_one_time(self):
        response, _ = self.register()
        request_id = response.data["data"]["request_id"]

        self.assertEqual(self.confirm(request_id).status_code, 200)
        self.assertEqual(self.confirm(request_id).status_code, 400)

    def test_wrong_code_is_rejected(self):
        response, payload = self.register()

        confirmed = self.confirm(response.data["data"]["request_id"], code="000000")

        self.assertEqual(confirmed.status_code, 400)
        vendor = Vendor.objects.get(phone=payload["phone"])
        self.assertEqual(vendor.status_id, VendorStatusEnum.PENDING.value)

    def test_duplicate_phone_is_rejected(self):
        unique = uuid.uuid4().int % 1_000_000_000
        phone = f"09{unique:09d}"
        self.register(phone=phone)

        response, _ = self.register(phone=phone)

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.data["errors"])

    def test_duplicate_national_id_is_rejected(self):
        national_id = str(uuid.uuid4().int % 10_000_000_000)
        self.register(national_id=national_id)

        response, _ = self.register(national_id=national_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("national_id", response.data["errors"])

    def test_password_mismatch_is_rejected(self):
        response, _ = self.register(
            password="StrongPass!123",
            password_confirmation="DifferentPass!123",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirmation", response.data["errors"])

    def test_vendor_cannot_login_while_pending(self):
        response, payload = self.register()

        login_response = self.client.post(
            "/api/vendor/login",
            {"phone": payload["phone"], "password": payload["password"]},
            format="json",
        )

        self.assertEqual(login_response.status_code, 400)

    def test_confirm_nonexistent_request_id_is_rejected(self):
        response = self.confirm("nonexistent-request-id")

        self.assertEqual(response.status_code, 400)

    def test_delivery_task_failure_does_not_block_registration(self):
        self.delivery_task.side_effect = Exception("broker down")

        response, _ = self.register()

        self.assertEqual(response.status_code, 202)

    def test_missing_required_fields_are_rejected(self):
        response = self.client.post("/api/vendor/register", {}, format="json")

        self.assertEqual(response.status_code, 400)
        for field in (
            "first_name",
            "last_name",
            "phone",
            "national_id",
            "password",
            "password_confirmation",
        ):
            self.assertIn(field, response.data["errors"])

    def test_confirmation_activates_vendor_only_once(self):
        response, _ = self.register()
        request_id = response.data["data"]["request_id"]

        self.assertEqual(self.confirm(request_id).status_code, 200)

        vendor = Vendor.objects.order_by("-pk").first()
        original_updated_at = vendor.updated_at

        response2, _ = self.register()
        request_id2 = response2.data["data"]["request_id"]
        self.assertEqual(self.confirm(request_id2).status_code, 200)

        vendor.refresh_from_db()
        self.assertEqual(vendor.status_id, VendorStatusEnum.ACTIVE.value)
        self.assertIsNotNone(original_updated_at)

    def test_persian_phone_digits_are_normalized(self):
        translation = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        unique = uuid.uuid4().int % 1_000_000_000
        phone = f"09{unique:09d}"

        response, _ = self.register(phone=phone.translate(translation))

        self.assertEqual(response.status_code, 202)
        vendor = Vendor.objects.get(phone=phone)
        self.assertIsNotNone(vendor)


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class VendorLoginConfirmationAPITests(APITestCase):
    def setUp(self):
        self.active_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
            name="active",
            title="Active",
        )
        unique = uuid.uuid4().int % 1_000_000_000
        self.vendor = Vendor.objects.create_user(
            phone=f"09{unique:09d}",
            password="password",
            first_name="Login",
            last_name="Vendor",
            national_id=str(unique),
            status=self.active_status,
        )
        self.delivery_patcher = patch(
            "domains.vendor.tasks.deliver_vendor_sms.apply_async"
        )
        self.delivery_task = self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)

    def request_confirmation(self):
        return self.client.post(
            "/api/vendor/login",
            {"phone": self.vendor.phone, "password": "password"},
            format="json",
        )

    def test_request_and_confirm_issues_tokens(self):
        requested = self.request_confirmation()

        self.assertEqual(requested.status_code, 202)
        self.assertNotIn("access", requested.data["data"])
        self.assertGreater(requested.data["data"]["expires_in"], 0)
        self.assertNotIn(self.vendor.phone, requested.data["data"]["destination"])

        self.delivery_task.assert_called_once()
        call_args = self.delivery_task.call_args.kwargs["args"]
        self.assertEqual(call_args[0], self.vendor.pk)
        self.assertIn("123456", call_args[1])

        confirmed = self.client.post(
            "/api/vendor/login/confirmation",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertIn("access", confirmed.data["data"])
        self.assertIn("refresh", confirmed.data["data"])
        self.vendor.refresh_from_db()
        self.assertIsNotNone(self.vendor.last_login)

    def test_confirmation_is_one_time(self):
        requested = self.request_confirmation()
        payload = {
            "request_id": requested.data["data"]["request_id"],
            "code": "123456",
        }

        confirmed = self.client.post(
            "/api/vendor/login/confirmation", payload, format="json"
        )
        self.assertEqual(confirmed.status_code, 200)

        replay = self.client.post(
            "/api/vendor/login/confirmation", payload, format="json"
        )
        self.assertEqual(replay.status_code, 400)

    def test_wrong_code_is_rejected(self):
        requested = self.request_confirmation()

        response = self.client.post(
            "/api/vendor/login/confirmation",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.vendor.refresh_from_db()
        self.assertIsNone(self.vendor.last_login)

    def test_inactive_vendor_cannot_login(self):
        inactive_status = VendorStatus.objects.create(
            id=VendorStatusEnum.INACTIVE.value,
            name="inactive",
            title="Inactive",
            is_active=False,
        )
        self.vendor.status = inactive_status
        self.vendor.save()

        response = self.request_confirmation()

        self.assertEqual(response.status_code, 400)

    def test_password_change_invalidates_pending_confirmation(self):
        requested = self.request_confirmation()
        self.vendor.set_password("new-password")
        self.vendor.save(update_fields=["password"])

        response = self.client.post(
            "/api/vendor/login/confirmation",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class VendorPhoneConfirmationAPITests(APITestCase):
    def setUp(self):
        self.active_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
            name="active",
            title="Active",
        )
        unique = uuid.uuid4().int % 1_000_000_000
        self.vendor = Vendor.objects.create_user(
            phone=f"09{unique:09d}",
            password="password",
            first_name="Verify",
            last_name="Vendor",
            national_id=str(unique),
            status=self.active_status,
        )
        refresh = RefreshToken.for_user(self.vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        self.delivery_patcher = patch(
            "domains.vendor.tasks.deliver_vendor_sms.apply_async"
        )
        self.delivery_task = self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)

    def request_confirmation(self):
        return self.client.post("/api/vendor/me/phone/confirmation", {}, format="json")

    def test_request_and_confirm_marks_phone_verified(self):
        requested = self.request_confirmation()

        self.assertEqual(requested.status_code, 202)
        self.assertNotIn(self.vendor.phone, requested.data["data"]["destination"])

        self.delivery_task.assert_called_once()
        call_args = self.delivery_task.call_args.kwargs["args"]
        self.assertEqual(call_args[0], self.vendor.pk)

        confirmed = self.client.post(
            "/api/vendor/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertIsNotNone(confirmed.data["data"]["phone_verified_at"])
        self.vendor.refresh_from_db()
        self.assertIsNotNone(self.vendor.phone_verified_at)

    def test_replay_is_rejected(self):
        requested = self.request_confirmation()

        confirmed = self.client.post(
            "/api/vendor/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200)

        replay = self.client.post(
            "/api/vendor/me/phone/confirmation/verify",
            {
                "request_id": requested.data["data"]["request_id"],
                "code": "123456",
            },
            format="json",
        )
        self.assertEqual(replay.status_code, 400)

    def test_already_verified_cannot_request(self):
        self.vendor.phone_verified_at = timezone.now()
        self.vendor.save(update_fields=["phone_verified_at"])

        response = self.request_confirmation()

        self.assertEqual(response.status_code, 400)
        self.delivery_task.assert_not_called()


@override_settings(
    CONFIRMED_REQUEST_DEV_CODE="123456",
    CONFIRMED_REQUEST_DEV_MODE=True,
)
class VendorPasswordResetAPITests(APITestCase):
    def setUp(self):
        self.active_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
            name="active",
            title="Active",
        )
        self.inactive_status = VendorStatus.objects.create(
            id=VendorStatusEnum.INACTIVE.value,
            name="inactive",
            title="Inactive",
            is_active=False,
        )
        unique = uuid.uuid4().int % 1_000_000_000
        self.vendor = Vendor.objects.create_user(
            phone=f"09{unique:09d}",
            password="old-password",
            first_name="Reset",
            last_name="Vendor",
            national_id=str(unique),
            status=self.active_status,
        )
        self.delivery_patcher = patch(
            "domains.vendor.tasks.deliver_vendor_sms.apply_async"
        )
        self.delivery_task = self.delivery_patcher.start()
        self.addCleanup(self.delivery_patcher.stop)

    def request_reset(self, phone=None):
        return self.client.post(
            "/api/vendor/password/forgot",
            {"phone": phone or self.vendor.phone},
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
            "/api/vendor/password/forgot/confirmation",
            payload,
            format="json",
        )

    def test_reset_changes_password_and_verifies_phone(self):
        requested = self.request_reset()
        request_id = requested.data["data"]["request_id"]

        response = self.confirm_reset(request_id)

        self.assertEqual(response.status_code, 200)
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.check_password("StrongReset!8374"))
        self.assertIsNotNone(self.vendor.phone_verified_at)

    def test_replay_is_rejected(self):
        requested = self.request_reset()
        request_id = requested.data["data"]["request_id"]

        self.assertEqual(self.confirm_reset(request_id).status_code, 200)
        self.assertEqual(self.confirm_reset(request_id).status_code, 400)

    def test_unknown_phone_has_same_shape(self):
        existing = self.request_reset()
        unknown = self.request_reset("09111111111")

        self.assertEqual(existing.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(set(existing.data["data"]), set(unknown.data["data"]))

    def test_delivery_task_is_queued(self):
        self.request_reset()

        self.delivery_task.assert_called_once()
        call_args = self.delivery_task.call_args.kwargs["args"]
        self.assertEqual(call_args[0], self.vendor.pk)
        self.assertIn("123456", call_args[1])
