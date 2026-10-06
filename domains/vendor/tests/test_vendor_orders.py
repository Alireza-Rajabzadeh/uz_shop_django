"""The seller's order surface over HTTP.

The platform's order reads are admin-gated, so these routes are the only
window a seller has on an order. What has to hold is therefore three things:
the list answers only for the caller's own business, another seller's order
is a 404 rather than somebody else's data, and the action vocabulary stops at
fulfillment — cancel, payment approval and refunds belong to the platform
even though the seeded action table marks them admin-usable.
"""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from domains.business.models import BusinessProfile
from domains.customer.models import Customer, CustomerStatus
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
)
from domains.vendor.models import Vendor, VendorStatus


class VendorOrderApiFixture(APITestCase):
    def setUp(self):
        MarketplaceOrderSeeder().run()

        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        self.customer = Customer.objects.create_user(
            phone="09120000801",
            password="password",
            first_name="Vendor",
            last_name="Orders",
            customer_code="CUS-VOR-001",
            status=CustomerStatus.objects.create(name="vor-active", title="Active"),
        )

        self.vendor = Vendor.objects.create(
            phone="+9990000081",
            first_name="Seller",
            last_name="One",
            national_id="0000000081",
            vendor_code="VEN-VOR-001",
            status=self.vendor_status,
        )
        # inventory.0022 seeds a vendor-less profile at id=1 for the migrated
        # rows; a seller has to be attached to it before any route answers.
        self.business, _ = BusinessProfile.objects.update_or_create(
            id=1,
            defaults={
                "vendor": self.vendor,
                "business_name": "Seller One",
                "display_name": "Seller One",
            },
        )

        self.other_vendor = Vendor.objects.create(
            phone="+9990000082",
            first_name="Seller",
            last_name="Two",
            national_id="0000000082",
            vendor_code="VEN-VOR-002",
            status=self.vendor_status,
        )
        self.other_business = BusinessProfile.objects.create(
            vendor=self.other_vendor,
            business_name="Seller Two",
            display_name="Seller Two",
        )

        self.order = self.make_order(self.business, status="payment_pending")
        self.other_order = self.make_order(self.other_business, status="payment_pending")

        self.as_vendor(self.vendor)

    # ───────────────────────── fixtures ─────────────────────────

    def make_order(self, business, *, status):
        return MarketplaceOrder.objects.create(
            customer=self.customer,
            business=business,
            status=MarketplaceOrderStatus.objects.get(name=status),
            address_info={"city_name": "Tehran"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="100.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )

    def as_vendor(self, vendor):
        refresh = RefreshToken.for_user(vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def as_anonymous(self):
        self.client.credentials()

    @staticmethod
    def action_codes(payload):
        return [action["code"] for action in payload["data"]["actions"]]


class VendorOrderListTests(VendorOrderApiFixture):
    def test_the_list_needs_a_seller(self):
        self.as_anonymous()

        response = self.client.get("/api/vendor/orders")

        self.assertIn(response.status_code, (401, 403))

    def test_the_list_answers_only_for_the_callers_business(self):
        response = self.client.get("/api/vendor/orders")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["data"]["results"]],
            [self.order.id],
        )

    def test_the_list_filters_by_status(self):
        paid = self.make_order(self.business, status="paid")

        response = self.client.get("/api/vendor/orders", {"status": "paid"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["data"]["results"]], [paid.id]
        )

    def test_the_list_offers_no_action_a_seller_cannot_take(self):
        confirmed = self.make_order(self.business, status="confirmed")

        response = self.client.get("/api/vendor/orders")

        row = next(
            row for row in response.data["data"]["results"] if row["id"] == confirmed.id
        )
        self.assertEqual(
            [action["code"] for action in row["available_actions"]], ["prepare"]
        )

    def test_statuses_are_filter_options(self):
        response = self.client.get("/api/vendor/orders/statuses")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"])
        self.assertIn("payment_pending", [row["name"] for row in response.data["data"]])


class VendorOrderDetailTests(VendorOrderApiFixture):
    def test_another_sellers_order_is_not_readable(self):
        response = self.client.get(f"/api/vendor/orders/{self.other_order.id}")

        self.assertEqual(response.status_code, 404)

    def test_the_detail_drops_the_platforms_actions(self):
        confirmed = self.make_order(self.business, status="confirmed")
        MarketplaceReturnRequest.objects.create(
            order=confirmed,
            customer=self.customer,
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6104337890123456",
        )

        response = self.client.get(f"/api/vendor/orders/{confirmed.id}")

        self.assertEqual(response.status_code, 200)
        # Status 210 offers cancel and prepare to the administrative actor.
        self.assertEqual(
            [
                action["code"]
                for action in response.data["data"]["available_actions"]
            ],
            ["prepare"],
        )
        # A seller decides on their own returns, so they always come back.
        self.assertEqual(
            [row["id"] for row in response.data["data"]["return_requests"]],
            [MarketplaceReturnRequest.objects.get().id],
        )


class VendorOrderActionTests(VendorOrderApiFixture):
    def test_the_actions_endpoint_needs_a_seller(self):
        self.as_anonymous()

        response = self.client.get(f"/api/vendor/orders/{self.order.id}/actions")

        self.assertIn(response.status_code, (401, 403))

    def test_a_pending_order_offers_the_seller_nothing(self):
        # Status 110 offers cancel to both actors; cancel is the platform's.
        response = self.client.get(f"/api/vendor/orders/{self.order.id}/actions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.action_codes(response.data), [])

    def test_another_sellers_actions_are_not_readable(self):
        response = self.client.get(f"/api/vendor/orders/{self.other_order.id}/actions")

        self.assertEqual(response.status_code, 404)

    def test_a_fulfillment_action_is_executed_and_attributed_to_the_seller(self):
        confirmed = self.make_order(self.business, status="confirmed")

        response = self.client.post(
            f"/api/vendor/orders/{confirmed.id}/actions/prepare", {}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status.name, "preparing")
        entry = confirmed.history.select_related("action").get()
        self.assertEqual(entry.action.code, "prepare")
        self.assertEqual(entry.user_id, self.vendor.id)
        self.assertEqual(entry.user_model, "vendor.Vendor")

    def test_cancel_is_refused_even_though_the_action_table_offers_it(self):
        confirmed = self.make_order(self.business, status="confirmed")

        response = self.client.post(
            f"/api/vendor/orders/{confirmed.id}/actions/cancel", {}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status.name, "confirmed")
        self.assertFalse(confirmed.history.exists())

    def test_another_sellers_order_cannot_be_moved(self):
        confirmed = self.make_order(self.other_business, status="confirmed")

        response = self.client.post(
            f"/api/vendor/orders/{confirmed.id}/actions/prepare", {}, format="json"
        )

        self.assertEqual(response.status_code, 404)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status.name, "confirmed")


class VendorOrderReturnActionTests(VendorOrderApiFixture):
    def make_return(self, order):
        return MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6104337890123456",
        )

    def test_a_seller_decides_on_their_own_return(self):
        request = self.make_return(self.order)

        response = self.client.post(
            f"/api/vendor/orders/{self.order.id}/returns/{request.id}/actions/approve",
            {"admin_note": "Accepted"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertEqual(request.admin_note, "Accepted")

    def test_another_sellers_return_cannot_be_decided(self):
        request = self.make_return(self.other_order)

        response = self.client.post(
            f"/api/vendor/orders/{self.other_order.id}/returns/{request.id}/actions/approve",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        request.refresh_from_db()
        self.assertEqual(request.status, "requested")

    def test_a_return_pointed_at_another_order_is_not_found(self):
        request = self.make_return(self.other_order)

        response = self.client.post(
            f"/api/vendor/orders/{self.order.id}/returns/{request.id}/actions/approve",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        request.refresh_from_db()
        self.assertEqual(request.status, "requested")
