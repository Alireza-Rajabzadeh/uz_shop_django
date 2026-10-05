"""The marketplace HTTP surface.

Both the customer routes and the admin routes are the shop's order views
with the flow swapped, so what is pinned here is that they answer from the
marketplace tables: an admin without ``marketplace.view_marketplaceorder``
is turned away, another customer's order is a 404, and a return created
over HTTP lands on a marketplace request rather than a shop one.
"""

from django.contrib.auth.models import User

from domains.customer.models import Customer
from domains.marketplace.models import (
    MarketplaceCart,
    MarketplaceOrder,
    MarketplaceOrderAction,
    MarketplaceOrderHistory,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
)
from domains.order.models import ReturnRequest

from .tests_checkout import MarketplaceCheckoutFixture


def error_keys(response):
    """The field names a refusal blamed, whatever DEBUG wrapped them in."""
    errors = response.json()["errors"]
    if isinstance(errors, dict) and "details" in errors:
        errors = errors["details"]
    if isinstance(errors, dict):
        return set(errors)
    return {str(errors)}


class MarketplaceApiFixture(MarketplaceCheckoutFixture):
    def an_order(self, quantity=1):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        return self.service.checkout_from_cart(self.customer)

    def a_delivered_order(self, quantity=1):
        order = self.an_order(quantity)
        order.status = MarketplaceOrderStatus.objects.get(id=300)
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at", "updated_at"])
        MarketplaceOrderHistory.objects.create(
            order=order,
            action=MarketplaceOrderAction.objects.get(code="deliver"),
            description="Delivered",
        )
        return order

    def cancel_history(self, order):
        return [
            entry
            for entry in order.history.select_related("action")
            if entry.action.code == "cancel"
        ]


class MarketplaceCustomerApiTests(MarketplaceApiFixture):
    def test_the_order_routes_needs_a_customer(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/marketplace/orders")

        self.assertIn(response.status_code, (401, 403))

    def test_the_order_list_returns_only_this_customer_s_orders(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000702",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-002",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)
        listing = self.client.get("/api/marketplace/orders")
        self.assertEqual(listing.json()["data"]["count"], 0)

        self.client.force_authenticate(self.customer)
        listing = self.client.get("/api/marketplace/orders")
        self.assertEqual(listing.json()["data"]["count"], 1)
        self.assertEqual(listing.json()["data"]["results"][0]["id"], order.id)

    def test_posting_an_order_checks_the_basket_out(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/marketplace/orders", format="json")

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["items"][0]["quantity"], 2)
        self.assertEqual(payload["status"]["name"], "payment_pending")

    def test_posting_an_empty_basket_is_refused(self):
        # An addressed basket with nothing in it, so the refusal below is
        # about the emptiness rather than about a missing address.
        MarketplaceCart.objects.create(
            customer=self.customer, address_info={"city_name": "MkCi"}
        )
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/marketplace/orders", format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", error_keys(response))
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_another_customer_s_order_is_not_readable(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000703",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-003",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)

        self.assertEqual(
            self.client.get(f"/api/marketplace/orders/{order.id}").status_code, 404
        )
        self.assertEqual(
            self.client.get(
                f"/api/marketplace/orders/{order.id}/actions"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/marketplace/orders/{order.id}/actions/cancel"
            ).status_code,
            404,
        )

    def test_the_actions_endpoint_offers_cancel_and_the_action_endpoint_cancels(self):
        order = self.an_order()
        self.client.force_authenticate(self.customer)

        actions = self.client.get(f"/api/marketplace/orders/{order.id}/actions")
        self.assertEqual(
            [action["code"] for action in actions.json()["data"]["actions"]],
            ["cancel"],
        )

        response = self.client.post(
            f"/api/marketplace/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "cancelled")
        order.refresh_from_db()
        self.assertEqual(order.status.name, "cancelled")
        self.assertEqual(len(self.cancel_history(order)), 1)

    def test_cancelling_another_customer_s_order_is_refused(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000704",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-004",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)
        response = self.client.post(
            f"/api/marketplace/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 404)

    def test_the_payment_methods_are_the_business_s_own(self):
        self.client.force_authenticate(self.customer)

        response = self.client.get("/api/marketplace/payment-methods")

        self.assertEqual(response.status_code, 200)
        methods = response.json()["data"]["methods"]
        self.assertIn("card_to_card", [method["code"] for method in methods])

    def test_a_return_can_be_created_listed_and_read_over_http(self):
        order = self.a_delivered_order()
        self.client.force_authenticate(self.customer)

        created = self.client.post(
            "/api/marketplace/returns",
            {
                "order_id": order.id,
                "reason": "Broken on arrival",
                "refund_destination_type": "card",
                "refund_destination_value": "6037991234567890",
                "items": [{"order_item_id": order.items.get().id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        body = created.json()["data"]
        self.assertEqual(body["status"], "requested")
        self.assertEqual(MarketplaceReturnRequest.objects.count(), 1)
        # Nothing was written to the shop's return table.
        self.assertEqual(ReturnRequest.objects.count(), 0)

        listing = self.client.get("/api/marketplace/returns")
        self.assertEqual(listing.json()["data"]["count"], 1)

        detail = self.client.get(f"/api/marketplace/returns/{body['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["id"], body["id"])

    def test_an_order_outside_the_return_window_is_refused(self):
        order = self.an_order()
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            "/api/marketplace/returns",
            {
                "order_id": order.id,
                "reason": "Too late",
                "refund_destination_type": "card",
                "refund_destination_value": "6037991234567890",
                "items": [{"order_item_id": order.items.get().id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("order_id", error_keys(response))
        self.assertEqual(MarketplaceReturnRequest.objects.count(), 0)


class MarketplaceAdminApiTests(MarketplaceApiFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("mk-admin", password="password")
        self.client.force_authenticate(self.admin)

    def test_the_admin_list_reads_marketplace_orders(self):
        order = self.an_order()

        response = self.client.get("/api/marketplace/admin/orders")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(row["id"], order.id)
        self.assertEqual(row["status"]["name"], "payment_pending")
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["totals"]["total_amount"], str(order.total_amount))

    def test_the_admin_list_filters_by_status_and_returns(self):
        order = self.an_order()
        MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status="requested",
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"status": "paid"}
            ).json()["data"]["count"],
            0,
        )
        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"search": "Marketplace"}
            ).json()["data"]["count"],
            1,
        )
        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"has_active_returns": "true"}
            ).json()["data"]["count"],
            1,
        )

    def test_the_admin_status_options_come_from_the_marketplace_table(self):
        MarketplaceOrderStatus.objects.create(
            id=999, name="mk_only", fa_name="فقط مارکت‌پلیس", description="Marketplace only"
        )

        response = self.client.get("/api/marketplace/admin/statuses")

        self.assertEqual(response.status_code, 200)
        names = [status["name"] for status in response.json()["data"]]
        self.assertIn("mk_only", names)

    def test_the_admin_detail_carries_actions_returns_and_history(self):
        order = self.a_delivered_order()

        response = self.client.get(f"/api/marketplace/admin/orders/{order.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"]["name"], "delivered")
        self.assertEqual(data["customer"]["id"], self.customer.id)
        self.assertEqual(data["return_requests"], [])
        self.assertEqual(
            [entry["action"]["code"] for entry in data["history"]], ["deliver"]
        )

    def test_the_admin_can_execute_an_action(self):
        order = self.an_order()

        response = self.client.post(
            f"/api/marketplace/admin/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "cancelled")

    def test_the_admin_can_decide_on_a_return(self):
        order = self.a_delivered_order()
        request = MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status="requested",
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

        response = self.client.post(
            f"/api/marketplace/admin/orders/{order.id}/returns/{request.id}/actions/approve",
            {"admin_note": "Accepted"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertIsNotNone(request.approved_at)
        self.assertEqual(request.admin_note, "Accepted")
        returned = response.json()["data"]["return_requests"][0]
        self.assertEqual(returned["id"], request.id)
        self.assertEqual(returned["status"], "approved")

    def test_an_admin_without_the_marketplace_order_permission_is_refused(self):
        self.client.force_authenticate(
            User.objects.create_user("mk-restricted", password="password")
        )

        for method, url in (
            ("get", "/api/marketplace/admin/orders"),
            ("get", "/api/marketplace/admin/orders/1"),
            ("post", "/api/marketplace/admin/orders/1/actions/cancel"),
        ):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403, url)
