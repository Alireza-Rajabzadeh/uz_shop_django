from decimal import Decimal

from core.management.seeders.order import OrderSeeder
from domains.marketplace.models import (
    MarketplaceOrderAction,
    MarketplaceOrderHistory,
    MarketplaceReturnRequest,
)
from domains.order.models import Order, OrderStatus

from .tests_checkout import MarketplaceCheckoutFixture


class MarketplaceOrderReadTests(MarketplaceCheckoutFixture):
    """Reading a marketplace order back out.

    The whole read layer is inherited from ``BaseOrderService``; what is
    pinned here is that it reaches for the marketplace tables, so listing a
    customer's marketplace orders cannot drag a shop order in with them and
    an admin detail cannot report a shop audit row as this order's history.
    """

    def checked_out_order(self, quantity=1):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        return self.service.checkout_from_cart(self.customer)

    def an_open_return(self, order, *, status="requested"):
        return MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status=status,
            reason="Broken on arrival",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

    def test_a_customer_only_sees_their_marketplace_orders(self):
        marketplace_order = self.checked_out_order()
        # A shop order for the very same customer, on the shop's own status.
        OrderSeeder().run()
        Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={},
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("500.00"),
        )

        orders = self.service.list_orders(self.customer)

        self.assertEqual([order["id"] for order in orders], [marketplace_order.id])

    def test_the_customer_payload_carries_the_priced_snapshot_and_its_actions(self):
        order = self.checked_out_order()

        payload = self.service.get_order(self.customer, order.id)

        self.assertEqual(payload["id"], order.id)
        self.assertEqual(payload["status"]["name"], "payment_pending")
        self.assertIsNotNone(payload["status"]["description"])
        line = payload["items"][0]
        self.assertEqual(line["sku"], order.items.get().sku)
        self.assertEqual(line["unit_price"], "100.00")
        self.assertEqual(payload["totals"]["total_amount"], str(order.total_amount))
        self.assertEqual(
            [action["code"] for action in payload["available_actions"]],
            ["cancel"],
        )
        self.assertEqual(payload["return_requests"], [])

    def test_the_customer_payload_reports_this_flow_s_returns(self):
        order = self.checked_out_order()
        request = self.an_open_return(order)

        payload = self.service.get_order(self.customer, order.id)

        self.assertEqual(
            [item["id"] for item in payload["return_requests"]], [request.id]
        )
        self.assertEqual(
            payload["return_requests"][0]["refund_destination_masked"], "****7890"
        )

    def test_the_admin_detail_reads_marketplace_status_actions_and_history(self):
        order = self.checked_out_order()
        MarketplaceOrderHistory.objects.create(
            order=order,
            action=MarketplaceOrderAction.objects.get(code="cancel"),
            description="Order action 'Cancel order' executed by admin.",
        )

        payload = self.service.get_order_admin(order.id)

        self.assertEqual(payload["status"]["name"], "payment_pending")
        self.assertEqual(
            [action["code"] for action in payload["available_actions"]],
            ["cancel"],
        )
        self.assertEqual(payload["customer"]["id"], self.customer.id)
        self.assertEqual(payload["return_requests"], [])
        self.assertEqual(
            [entry["action"]["code"] for entry in payload["history"]],
            ["cancel"],
        )

    def test_the_admin_detail_can_leave_returns_out(self):
        order = self.checked_out_order()
        self.an_open_return(order, status="approved")

        with_returns = self.service.get_order_admin(order.id, include_returns=True)
        without_returns = self.service.get_order_admin(
            order.id, include_returns=False
        )

        self.assertEqual(len(with_returns["return_requests"]), 1)
        self.assertNotIn("return_requests", without_returns)

    def test_the_admin_list_filters_by_status_search_and_returns(self):
        order = self.checked_out_order()
        self.an_open_return(order)

        self.assertEqual(len(self.service.list_orders_admin()), 1)
        self.assertEqual(self.service.list_orders_admin(status="paid"), [])
        self.assertEqual(
            len(self.service.list_orders_admin(search="Marketplace")), 1
        )
        self.assertEqual(self.service.list_orders_admin(search="no-match"), [])
        self.assertEqual(
            len(self.service.list_orders_admin(has_active_returns=True)), 1
        )
        self.assertEqual(len(self.service.list_orders_admin(has_returns=True)), 1)
        self.assertEqual(
            self.service.list_orders_admin(has_active_returns=True, status="paid"), []
        )
        self.assertNotIn(
            "return_summary", self.service.list_orders_admin()[0]
        )
        summary = self.service.list_orders_admin(include_returns=True)[0][
            "return_summary"
        ]
        self.assertEqual(
            summary,
            {"count": 1, "open_count": 1, "latest_status": "requested"},
        )
