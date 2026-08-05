from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.customers import CustomerSeeder, TEST_CUSTOMER_PASSWORD
from core.services import ConfirmedRequestService
from core.utils import normalize_phone
from domains.customer.models import (
    Customer,
    CustomerAddress,
    CustomerPreference,
    CustomerStatus,
)
from domains.location.models import City, Country, State
from domains.notifications.services import NotificationError


class CustomerPhoneNormalizationTests(TestCase):
    def test_persian_and_arabic_digits_are_stored_as_ascii(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="۰۹۱۲-۳۴۵-۶۷۸۹",
            password="password",
            first_name="Phone",
            last_name="Test",
            customer_code="CUS-PHONE",
            status=status,
        )

        self.assertEqual(customer.phone, "09123456789")
        self.assertEqual(normalize_phone("٠٩١٢ ٣٤٥ ٦٧٨٩"), "09123456789")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create_user(
                phone="0912 345 6789",
                password="password",
                first_name="Duplicate",
                last_name="Phone",
                customer_code="CUS-PHONE-DUPLICATE",
                status=status,
            )

    def test_database_rejects_noncanonical_bulk_update(self):
        status = CustomerStatus.objects.create(name="active", title="Active")
        customer = Customer.objects.create_user(
            phone="09123456789",
            password="password",
            first_name="Phone",
            last_name="Constraint",
            customer_code="CUS-PHONE-CONSTRAINT",
            status=status,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.filter(pk=customer.pk).update(phone="invalid")


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


class AdminCustomerAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.inactive = CustomerStatus.objects.create(name="inactive", title="Inactive")
        self.customer = Customer.objects.create_user(
            phone="09120000001", password="password", first_name="Ali",
            last_name="Ahmadi", customer_code="CUS-10001", status=self.active,
            email="ali@example.com", gender="male",
        )
        self.other_customer = Customer.objects.create_user(
            phone="09120000002", password="password", first_name="Sara",
            last_name="Karimi", customer_code="CUS-10002", status=self.inactive,
        )
        self.admin = User.objects.create_user(
            username="customer-admin", password="password", is_staff=True
        )

    def grant(self, *codenames):
        permissions = Permission.objects.filter(
            content_type__app_label="customer", codename__in=codenames
        )
        self.admin.user_permissions.add(*permissions)
        self.admin = User.objects.get(pk=self.admin.pk)
        self.client.force_authenticate(self.admin)

    def list_ids(self, **params):
        response = self.client.get("/api/customer/customers", params)
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.data["data"]["results"]]

    def test_customer_list_requires_model_permission(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 403)

        self.grant("view_customer")
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 2)

    def test_customer_token_is_rejected_from_admin_api(self):
        refresh = RefreshToken.for_user(self.customer)
        refresh["user_type"] = "customer"
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 401)

    def test_customer_filters_ordering_and_update_keep_code_immutable(self):
        self.grant("view_customer", "change_customer")
        response = self.client.get(
            f"/api/customer/customers?search=ali&status_id={self.active.id}&ordering=-phone"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["id"], self.customer.id)

        response = self.client.patch(
            f"/api/customer/customers/{self.customer.id}",
            {"first_name": "Alireza", "status_id": self.inactive.id, "customer_code": "CHANGED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Alireza")
        self.assertEqual(self.customer.status, self.inactive)
        self.assertEqual(self.customer.customer_code, "CUS-10001")

    def test_exact_id_and_existing_field_filters_are_anded(self):
        self.grant("view_customer")

        self.assertEqual(
            self.list_ids(
                id=self.customer.id,
                customer_code="1000",
                first_name="AL",
                last_name="mad",
                email="EXAMPLE",
                phone="000001",
                status_id=self.active.id,
                gender="male",
            ),
            [self.customer.id],
        )
        self.assertEqual(
            self.list_ids(id=self.customer.id, first_name="Sara"),
            [],
        )

        self.assertEqual(
            self.list_ids(ordering="gender"),
            [self.customer.id, self.other_customer.id],
        )

    def test_global_search_is_or_across_text_and_anded_with_filters(self):
        self.grant("view_customer")

        self.assertEqual(
            self.list_ids(search="CUS-10002", status_id=self.inactive.id),
            [self.other_customer.id],
        )
        self.assertEqual(
            self.list_ids(search="CUS-10002", status_id=self.active.id),
            [],
        )

    def test_date_of_birth_range_is_inclusive(self):
        self.grant("view_customer")
        self.customer.date_of_birth = date(1990, 5, 10)
        self.customer.save(update_fields=["date_of_birth"])
        self.other_customer.date_of_birth = date(1990, 5, 11)
        self.other_customer.save(update_fields=["date_of_birth"])

        self.assertEqual(
            self.list_ids(date_of_birth_from="1990-05-10", date_of_birth_to="1990-05-10"),
            [self.customer.id],
        )

    def test_verification_filters_are_tri_state_and_include_nulls_for_false(self):
        self.grant("view_customer")
        verified_at = timezone.make_aware(datetime(2026, 7, 20, 12, 0))
        Customer.objects.filter(pk=self.customer.pk).update(
            email_verified_at=verified_at,
            phone_verified_at=None,
        )
        Customer.objects.filter(pk=self.other_customer.pk).update(
            email_verified_at=None,
            phone_verified_at=verified_at,
        )

        self.assertEqual(set(self.list_ids()), {self.customer.id, self.other_customer.id})
        self.assertEqual(self.list_ids(email_verified="true"), [self.customer.id])
        self.assertEqual(self.list_ids(email_verified="false"), [self.other_customer.id])
        self.assertEqual(self.list_ids(phone_verified="true"), [self.other_customer.id])
        self.assertEqual(self.list_ids(phone_verified="false"), [self.customer.id])

    def test_login_presence_and_calendar_date_range_are_inclusive(self):
        self.grant("view_customer")
        Customer.objects.filter(pk=self.customer.pk).update(
            last_login=timezone.make_aware(datetime(2026, 7, 20, 23, 59, 59))
        )

        self.assertEqual(self.list_ids(has_logged_in="true"), [self.customer.id])
        self.assertEqual(self.list_ids(has_logged_in="false"), [self.other_customer.id])
        self.assertEqual(
            self.list_ids(last_login_from="2026-07-20", last_login_to="2026-07-20"),
            [self.customer.id],
        )

    def test_created_and_updated_calendar_date_ranges_are_inclusive_and_combine(self):
        self.grant("view_customer")
        boundary = timezone.make_aware(datetime(2026, 7, 15, 23, 59, 59))
        outside = timezone.make_aware(datetime(2026, 7, 16, 0, 0))
        Customer.objects.filter(pk=self.customer.pk).update(
            created_at=boundary,
            updated_at=boundary,
        )
        Customer.objects.filter(pk=self.other_customer.pk).update(
            created_at=outside,
            updated_at=outside,
        )

        self.assertEqual(
            self.list_ids(
                created_at_from="2026-07-15",
                created_at_to="2026-07-15",
                updated_at_from="2026-07-15",
                updated_at_to="2026-07-15",
                email_verified="false",
            ),
            [self.customer.id],
        )

    def test_invalid_date_ranges_return_field_errors(self):
        self.grant("view_customer")

        for prefix in ("date_of_birth", "last_login", "created_at", "updated_at"):
            with self.subTest(prefix=prefix):
                response = self.client.get(
                    "/api/customer/customers",
                    {f"{prefix}_from": "2026-07-21", f"{prefix}_to": "2026-07-20"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(f"{prefix}_to", response.data["errors"])


class CustomerAddressAPITests(APITestCase):
    def setUp(self):
        status = CustomerStatus.objects.create(name="address-active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09121111111", password="password", first_name="One",
            last_name="Customer", customer_code="CUS-20001", status=status,
        )
        self.other_customer = Customer.objects.create_user(
            phone="09122222222", password="password", first_name="Other",
            last_name="Customer", customer_code="CUS-20002", status=status,
        )
        self.country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        self.other_country = Country.objects.create(name="Turkey", code="TR", phone_code="+90")
        self.state = State.objects.create(country=self.country, name="Tehran")
        self.other_state = State.objects.create(country=self.other_country, name="Istanbul")
        self.city = City.objects.create(state=self.state, name="Tehran")
        self.other_city = City.objects.create(state=self.other_state, name="Istanbul")
        self.address = self.make_address(self.customer, "Home")
        self.other_address = self.make_address(self.other_customer, "Other home")
        self.admin = User.objects.create_user(
            username="address-admin", password="password", is_staff=True
        )
        permissions = Permission.objects.filter(
            content_type__app_label="customer",
            codename__in=[
                "view_customeraddress", "add_customeraddress",
                "change_customeraddress", "delete_customeraddress",
            ],
        )
        self.admin.user_permissions.add(*permissions)
        self.client.force_authenticate(self.admin)

    def make_address(self, customer, title, is_default=False):
        return CustomerAddress.objects.create(
            customer=customer, title=title, country=self.country, state=self.state,
            city=self.city, postal_code="1234567890", address_line1="Street 1",
            is_default=is_default,
        )

    def payload(self, **overrides):
        data = {
            "title": "Office", "country": self.country.id, "state": self.state.id,
            "city": self.city.id, "postal_code": "9876543210",
            "address_line1": "Street 2", "is_default": False,
        }
        data.update(overrides)
        return data

    def test_nested_address_cannot_cross_customer_boundary(self):
        url = f"/api/customer/customers/{self.customer.id}/addresses/{self.other_address.id}"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"title": "Stolen"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.other_address.refresh_from_db()
        self.assertEqual(self.other_address.title, "Other home")

    def test_address_create_update_delete_and_hierarchy_validation(self):
        list_url = f"/api/customer/customers/{self.customer.id}/addresses"
        response = self.client.post(list_url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        address_id = response.data["data"]["id"]

        detail_url = f"{list_url}/{address_id}"
        response = self.client.patch(detail_url, {"title": "Work"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Work")

        response = self.client.post(
            list_url, self.payload(state=self.other_state.id), format="json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(detail_url, {"city": self.other_city.id}, format="json")
        self.assertEqual(response.status_code, 400)

        self.assertEqual(self.client.delete(detail_url).status_code, 200)
        self.assertFalse(CustomerAddress.objects.filter(pk=address_id).exists())

    def test_setting_default_reassigns_and_database_rejects_duplicates(self):
        self.address.is_default = True
        self.address.save()
        list_url = f"/api/customer/customers/{self.customer.id}/addresses"
        response = self.client.post(
            list_url, self.payload(title="New default", is_default=True), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.address.refresh_from_db()
        self.assertFalse(self.address.is_default)
        self.assertEqual(
            CustomerAddress.objects.filter(customer=self.customer, is_default=True).count(), 1
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_address(self.customer, "Conflicting default", is_default=True)


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


class CustomerSeederTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        state = State.objects.create(country=country, name="Tehran")
        for index in range(1, 6):
            City.objects.create(state=state, name=f"Test City {index}")

    def test_customer_fixtures_are_complete_idempotent_and_isolated(self):
        seeder = CustomerSeeder()
        seeder.run()

        fixtures = Customer.objects.filter(email__endswith="@uzshop.local")
        self.assertEqual(fixtures.count(), 100)
        self.assertEqual(CustomerPreference.objects.filter(customer__in=fixtures).count(), 100)
        self.assertEqual(CustomerAddress.objects.filter(customer__in=fixtures).count(), 199)
        self.assertEqual(
            CustomerAddress.objects.filter(customer__in=fixtures, is_default=True).count(),
            100,
        )
        for status_id in range(1, 5):
            self.assertEqual(fixtures.filter(status_id=status_id).count(), 25)

        first = fixtures.get(phone="09990000001")
        self.assertTrue(first.check_password(TEST_CUSTOMER_PASSWORD))
        for address in CustomerAddress.objects.filter(customer__in=fixtures).select_related(
            "country", "state", "city"
        ):
            self.assertEqual(address.state.country_id, address.country_id)
            self.assertEqual(address.city.state_id, address.state_id)

        real_customer = Customer.objects.create_user(
            phone="09120000999",
            password="RealPassword123!",
            first_name="Real",
            last_name="Customer",
            email="real@example.com",
            customer_code="CUS-90000",
            status_id=1,
        )
        seeder.run()

        self.assertEqual(Customer.objects.filter(email__endswith="@uzshop.local").count(), 100)
        self.assertEqual(CustomerAddress.objects.filter(customer__in=fixtures).count(), 199)
        real_customer.refresh_from_db()
        self.assertEqual(real_customer.email, "real@example.com")
