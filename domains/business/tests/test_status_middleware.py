"""The project-wide business-status gate.

These tests use real minted bearer tokens through `client.credentials`,
so unlike `force_authenticate` fixtures every request here actually
passes through `core.middleware.business_status` before reaching DRF —
which is the whole point: one gate, applied to every vendor request,
reads included. The panel caches `businessStatus` client-side, so the
server-side allowlist is what makes that cache safe to trust.
"""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.middleware.business_status import _is_auth_path
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
        # a ban means nothing changes. It is also what stops the boot-read
        # exemption from being a hole — `/business/profile` is a boot path,
        # so a write to it must not ride along with the status read.
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

    # --- reads --------------------------------------------------------------

    def test_boot_reads_stay_open_for_every_status(self):
        # The shell needs these four to render *why* it is refusing:
        # `/vendor/me` feeds AuthGuard, `/packages/me` feeds VendorInitGate,
        # the profile feeds BusinessStatusGate, and the catalog feeds the
        # badges. Denying one fails open or hides the notice entirely.
        for vendor in (self.active_vendor, self.banned_vendor, self.pending_vendor):
            self.as_vendor(vendor)
            response = self.client.get("/api/vendor/business/profile")
            self.assertNotEqual(response.status_code, 403)

    def test_pending_vendor_is_blocked_from_reading_the_panel(self):
        # The cache is refreshed only while the notice is showing, so an
        # ordinary page still asks — and the server says no regardless.
        self.as_vendor(self.pending_vendor)
        response = self.client.get("/api/vendor/products")
        self.assert_gate_denied(response, "business_confirmation_await")

    def test_banned_vendor_is_blocked_from_reading_the_panel(self):
        self.as_vendor(self.banned_vendor)
        response = self.client.get("/api/vendor/products")
        self.assert_gate_denied(response, "business_banned")

    def test_banned_vendor_is_not_lifted_by_business_information_reads(self):
        # The pending allowlist is deliberately not a banned allowlist,
        # for reads exactly as for writes.
        self.as_vendor(self.banned_vendor)
        response = self.client.get("/api/vendor/business/phones")
        self.assert_gate_denied(response, "business_banned")

    def test_active_vendor_reads_reach_the_view(self):
        self.as_vendor(self.active_vendor)
        response = self.client.get("/api/vendor/products")
        self.assertNotEqual(response.status_code, 403)

    def test_pending_vendor_may_read_the_onboarding_reference_data(self):
        # The wizard's platform list is reference data, not business data:
        # a pending vendor is expected to be filling their business in.
        self.as_vendor(self.pending_vendor)
        response = self.client.get("/api/business/public/social-medias")
        self.assertNotEqual(response.status_code, 403)

    def test_pending_vendor_may_read_the_location_options(self):
        # The business form's province/city selects read the shared location
        # vocabulary. Without these the wizard cannot save an address, so
        # they belong to the same reference allowlist as the lists above.
        self.as_vendor(self.pending_vendor)
        for path in (
            "/api/location/options/vendor/provinces",
            "/api/location/options/vendor/cities",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotEqual(response.status_code, 403)

    def test_banned_vendor_is_blocked_from_the_location_options(self):
        self.as_vendor(self.banned_vendor)
        response = self.client.get("/api/location/options/vendor/provinces")
        self.assert_gate_denied(response, "business_banned")

    def test_location_options_allowlist_is_read_only(self):
        # A reference read is not a write path: only safe methods pass.
        self.as_vendor(self.pending_vendor)
        response = self.client.post(
            "/api/location/options/vendor/provinces", {}, format="json"
        )
        self.assert_gate_denied(response, "business_confirmation_await")

    def test_inventory_location_options_stay_gated(self):
        # Warehouse/product lookups are operations, not the business form.
        self.as_vendor(self.pending_vendor)
        response = self.client.get("/api/vendor/location-options/countries")
        self.assert_gate_denied(response, "business_confirmation_await")

    def test_banned_vendor_is_blocked_from_the_onboarding_reference_data(self):
        self.as_vendor(self.banned_vendor)
        response = self.client.get("/api/business/public/social-medias")
        self.assert_gate_denied(response, "business_banned")

    def test_gate_denial_is_a_403_never_a_401(self):
        # The panel clears its tokens on 401 only. If a gate refusal ever
        # arrived as 401 the vendor would be bounced to the login screen
        # instead of being shown the notice that explains the refusal.
        self.as_vendor(self.banned_vendor)
        response = self.client.post("/api/vendor/products/create", {}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(response.status_code, 401)

    # --- pass-throughs -----------------------------------------------------

    def test_pending_vendor_may_still_update_business_information(self):
        # The write half of the same allowlist `test_boot_reads_stay_open_...`
        # covers for reads: everything under `/vendor/business/` is the
        # vendor's own, and filling it in is the point of pending.
        self.as_vendor(self.pending_vendor)
        response = self.client.patch("/api/vendor/business/profile", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_pending_vendor_may_still_write_business_information(self):
        self.as_vendor(self.pending_vendor)
        response = self.client.post(
            "/api/vendor/business/phones", {"phone": "09120000000"}, format="json"
        )
        self.assertNotEqual(response.status_code, 403)

    def test_active_vendor_writes_reach_the_view(self):
        # 400 is the view's own validation answering, i.e. the gate let it
        # through; anything but the gate's 403 proves the same.
        self.as_vendor(self.active_vendor)
        response = self.client.post("/api/vendor/warehouses", {}, format="json")
        self.assertNotEqual(response.status_code, 403)

    def test_anonymous_write_is_answered_by_dr_f_not_the_gate(self):
        self.client.credentials()
        response = self.client.post("/api/vendor/products", {}, format="json")
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

    # --- auth entry points -------------------------------------------------

    def test_pending_vendor_may_reach_login(self):
        # The panel attaches whatever token it still holds, so signing in
        # again while an older one is in local storage must not be gated:
        # the request that issues a fresh session is not business data. The
        # panel shows the pending notice only *after* the session exists.
        self.as_vendor(self.pending_vendor)
        response = self.client.post(
            "/api/vendor/login",
            {"phone": self.pending_vendor.phone, "password": "wrong-password"},
            format="json",
        )
        self.assertNotEqual(response.status_code, 403)

    def test_banned_vendor_may_reach_login(self):
        self.as_vendor(self.banned_vendor)
        response = self.client.post(
            "/api/vendor/login",
            {"phone": self.banned_vendor.phone, "password": "wrong-password"},
            format="json",
        )
        self.assertNotEqual(response.status_code, 403)

    def test_auth_entry_points_are_never_gated(self):
        for path in (
            "/api/vendor/login/confirmation",
            "/api/vendor/register",
            "/api/vendor/register/confirmation",
            "/api/vendor/password/forgot",
            "/api/vendor/password/forgot/confirmation",
        ):
            with self.subTest(path=path):
                self.as_vendor(self.pending_vendor)
                response = self.client.post(path, {}, format="json")
                self.assertNotEqual(response.status_code, 403)

    def test_auth_path_matching_ignores_a_trailing_slash(self):
        self.assertTrue(_is_auth_path("/api/vendor/login"))
        self.assertTrue(_is_auth_path("/api/vendor/login/"))
        self.assertFalse(_is_auth_path("/api/vendor/products"))

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
