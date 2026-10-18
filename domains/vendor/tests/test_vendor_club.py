"""The seller's own view of the vendor club.

Only reads are exposed. What has to hold is therefore three things: the routes
need a seller, a seller sees only their own membership and ledger, and there is
no write path at all — points move solely through ``PointsService``.
"""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.vendor.models import Vendor, VendorStatus
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)
from domains.vendors_club.services import PointsService


class VendorClubApiFixture(APITestCase):
    def setUp(self):
        self.status, _ = VendorStatus.objects.get_or_create(
            id=1, defaults={"name": "active", "title": "Active"}
        )
        self.vendor = Vendor.objects.create_user(
            phone="09120000801",
            password="pass1234",
            first_name="Seller",
            last_name="Club",
            national_id="0000000001",
            status=self.status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09120000802",
            password="pass1234",
            first_name="Other",
            last_name="Seller",
            national_id="0000000002",
            status=self.status,
        )
        self.activity = VendorClubActivity.objects.create(
            code="profile.completed", name="Complete profile", points=100
        )
        self.other_activity = VendorClubActivity.objects.create(
            code="order.delivered", name="Deliver an order", points=25
        )
        self.as_vendor(self.vendor)

    def as_vendor(self, vendor):
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def as_anonymous(self):
        self.client.credentials()

    def award(self, vendor=None, activity_code=None, reference_id="1"):
        return PointsService.award_points(
            vendor=vendor or self.vendor,
            activity_code=activity_code or self.activity.code,
            reference_type="order",
            reference_id=reference_id,
        )


class VendorClubMembershipApiTests(VendorClubApiFixture):
    def test_the_endpoint_needs_a_seller(self):
        self.as_anonymous()

        response = self.client.get("/api/vendor/club/membership")

        self.assertIn(response.status_code, (401, 403))

    def test_it_creates_the_membership_on_first_read(self):
        response = self.client.get("/api/vendor/club/membership")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["available_points"], 0)
        self.assertEqual(data["lifetime_points"], 0)
        self.assertIsNotNone(data["last_synced_at"])
        self.assertTrue(
            VendorClubMembership.objects.filter(vendor=self.vendor).exists()
        )

    def test_it_reports_the_awarded_balances(self):
        self.award()

        response = self.client.get("/api/vendor/club/membership")

        self.assertEqual(response.data["data"]["available_points"], 100)
        self.assertEqual(response.data["data"]["lifetime_points"], 100)

    def test_it_reports_only_the_callers_own_balances(self):
        self.award(activity_code=self.activity.code)
        self.award(vendor=self.other_vendor, activity_code=self.other_activity.code)

        response = self.client.get("/api/vendor/club/membership")

        self.assertEqual(response.data["data"]["available_points"], 100)

    def test_the_membership_offers_no_write_path(self):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(self.client, method)(
                "/api/vendor/club/membership", {}
            )
            self.assertEqual(response.status_code, 405)


class VendorClubTransactionApiTests(VendorClubApiFixture):
    def test_the_list_needs_a_seller(self):
        self.as_anonymous()

        response = self.client.get("/api/vendor/club/transactions")

        self.assertIn(response.status_code, (401, 403))

    def test_it_lists_the_callers_own_transactions_newest_first(self):
        self.award(reference_id="1")
        self.award(reference_id="2")

        response = self.client.get("/api/vendor/club/transactions")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["count"], 2)
        first = data["results"][0]
        self.assertEqual(first["transaction_type"], "earn")
        self.assertEqual(first["transaction_type_name"], "Earn")
        self.assertEqual(first["points"], 100)
        self.assertEqual(first["activity_code"], "profile.completed")
        self.assertEqual(first["activity_name"], "Complete profile")
        self.assertEqual(first["reference_type"], "order")
        self.assertEqual(first["reference_id"], "2")

    def test_it_never_shows_another_sellers_transactions(self):
        self.award(vendor=self.other_vendor)

        response = self.client.get("/api/vendor/club/transactions")

        self.assertEqual(response.data["data"]["results"], [])

    def test_the_ledger_offers_no_write_path(self):
        response = self.client.post("/api/vendor/club/transactions", {})

        self.assertEqual(response.status_code, 405)
        self.assertFalse(
            VendorClubPointTransaction.objects.filter(
                membership__vendor=self.vendor
            ).exists()
        )
