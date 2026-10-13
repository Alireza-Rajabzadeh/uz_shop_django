"""The project-wide business-status write gate.

These tests use real minted bearer tokens through `client.credentials`,
so unlike `force_authenticate` fixtures every request here actually
passes through `core.middleware.business_status` before reaching DRF —
which is the whole point: one gate, applied to every vendor write.
"""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business.models import BusinessProfile
from domains.vendor.models import Vendor, VendorStatus

PROFILE = {"business_name": "Uz Shop", "display_name": "Uz"}


class BusinessStatusMiddlewareTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vendor_status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active", "is_active": True}
        )
        cls.active_vendor = cls.make_vendor(
            "09120000001", BusinessStatusEnum.ACTIVE.value
        )
        cls.banned_vendor = cls.make_vendor(
            "09120000002", BusinessStatusEnum.BANNED.value
        )
        cls.pending_vendor = cls.make_vendor(
            "09120000003", BusinessStatusEnum.CONFIRMATION_AWAIT.value
        )
        # A registered vendor with no business yet: the gate must let the
        # registration write itself through.
        cls.vendorless_vendor = cls.make_vendor("09120000004", None)

    @classmethod
    def make_vendor(cls, phone, status_id):
        vendor = Vendor.objects.create(
            phone=phone,
            first_name="Seller",
            last_name=phone[-4:],
            national_id=f"123456{phone[-4:]}",
            vendor_code=f"S{phone[-4:]}",
            status=cls.vendor_status,
        )
        if status_id is not None:
            BusinessProfile.objects.create(
                vendor=vendor, status_id=status_id, **PROFILE
            )
        return vendor

    def as_vendor(self, vendor):
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def as_non_vendor(self):
        """A valid token whose claim is not `vendor` — customer/admin flows."""
        refresh = RefreshToken.for_user(self.active_vendor)
        refresh["user_type"] = "customer"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def assert_gate_denied(self, response, code):
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertTrue(body["message"])
        self.assertEqual(body["errors"]["code"], code)
        self.assertIsNone(body["data"])

    # --- denials -----------------------------------------------------------

    def test_banned_vendor_is_blocked_from_every_write(self):
        self.as_vendor(self.banned_vendor)
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assert_gate_denied(response, "business_banned")

    def test_banned_vendor_is_blocked_even_from_business_information(self):
        # The pending allowlist is deliberately not a banned allowlist:
        # a ban means nothing changes.
        self.as_vendor(self.banned_vendor)
        response = self.client.patch("/api/vendor/business/profile", {}, format="json")
        self.assert_gate_denied(response, "business_banned")

    def test_pending_vendor_is_blocked_from_operations(self):
        self.as_vendor(self.pending_vendor)
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assert_gate_denied(response, "business_confirmation_await")

    def test_pending_vendor_is_blocked_outside_the_vendor_namespace(self):
        # Content authoring lives under another root namespace; the gate
        # is claim-scoped, so it reaches it without a path list.
        self.as_vendor(self.pending_vendor)
        response = self.client.post(
            "/api/business-content/vendor/landing-pages", {}, format="json"
        )
        self.assert_gate_denied(response, "business_confirmation_await")

    # --- pass-throughs -----------------------------------------------------

    def test_pending_vendor_may_still_update_business_information(self):
        self.as_vendor(self.pending_vendor)
        response = self.client.patch("/api/vendor/business/profile", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_active_vendor_writes_reach_the_view(self):
        # 400 is the view's own validation answering, i.e. the gate let it
        # through; anything but the gate's 403 proves the same.
        self.as_vendor(self.active_vendor)
        response = self.client.post("/api/vendor/warehouses", {}, format="json")
        self.assertNotEqual(response.status_code, 403)

    def test_reads_stay_open_for_every_status(self):
        for vendor in (self.active_vendor, self.banned_vendor, self.pending_vendor):
            self.as_vendor(vendor)
            response = self.client.get("/api/vendor/business/profile")
            self.assertNotEqual(response.status_code, 403)

    def test_anonymous_write_is_answered_by_dr_f_not_the_gate(self):
        self.client.credentials()
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)

    def test_non_vendor_token_is_not_gated(self):
        self.as_non_vendor()
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        # Whatever DRF does with a foreign principal (401), it is not the
        # business-status gate's 403.
        self.assertNotEqual(response.status_code, 403)

    def test_undecodable_token_passes_to_dr_f(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assertNotEqual(response.status_code, 403)

    def test_vendor_without_a_business_is_not_gated(self):
        # No profile means no status to enforce — the registration write
        # itself runs in this state.
        self.as_vendor(self.vendorless_vendor)
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assertNotEqual(response.status_code, 403)

    # --- exposure ----------------------------------------------------------

    def test_status_is_exposed_but_not_writable_by_the_vendor(self):
        self.as_vendor(self.pending_vendor)

        data = self.client.get("/api/vendor/business/profile").json()["data"]
        self.assertEqual(data["status"], BusinessStatusEnum.CONFIRMATION_AWAIT.value)
        self.assertEqual(data["status_code"], "confirmation_await")

        # The allowlisted PATCH runs, but an attempt to promote itself is
        # ignored: `status` is read-only for vendors.
        self.client.patch(
            "/api/vendor/business/profile",
            {"status": BusinessStatusEnum.ACTIVE.value},
            format="json",
        )
        data = self.client.get("/api/vendor/business/profile").json()["data"]
        self.assertEqual(data["status_code"], "confirmation_await")
