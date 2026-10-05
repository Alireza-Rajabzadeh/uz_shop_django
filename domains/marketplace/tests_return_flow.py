from datetime import datetime

from django.utils import timezone

from domains.inventory.models import InventorySupply, InventorySupplyConsumption
from domains.marketplace.models import (
    MarketplaceOrderAction,
    MarketplaceOrderHistory,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
)
from domains.marketplace.services.return_service import (
    MarketplaceReturnRequestService,
)
from domains.order.models import ReturnRequest

from .tests_checkout import MarketplaceCheckoutFixture


class MarketplaceReturnFlowTests(MarketplaceCheckoutFixture):
    """Returns for marketplace orders.

    The rules are inherited, so what is pinned here is that the flow reaches
    marketplace rows: the request it writes, the audit row it dates delivery
    from, the order it reads, and the cost layers it puts back.
    """

    def setUp(self):
        super().setUp()
        self.returns = MarketplaceReturnRequestService()

    def delivered_order(self, quantity=2):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        order = self.service.checkout_from_cart(self.customer)
        self.supply = InventorySupply.objects.create(
            variant=variant,
            warehouse=self.warehouse,
            quantity=10,
            remaining_quantity=10,
            unit_buy_price="40.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            received_at=timezone.make_aware(datetime(2026, 1, 11, 12, 0)),
        )
        self.service.consume_reservations(order)
        order.status = MarketplaceOrderStatus.objects.get(id=300)
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at", "updated_at"])
        MarketplaceOrderHistory.objects.create(
            order=order,
            action=MarketplaceOrderAction.objects.get(code="deliver"),
            description="Delivered",
        )
        return order

    def request_return(self, order, *, quantity=2):
        return self.returns.create(
            self.customer,
            order_id=order.id,
            reason="Damaged in transit",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
            items=[{"order_item_id": order.items.get().id, "quantity": quantity}],
        )

    # ───────────────────────── eligibility ─────────────────────────

    def test_a_delivered_marketplace_order_is_eligible(self):
        order = self.delivered_order()

        self.assertTrue(MarketplaceReturnRequestService.is_eligible(order))
        self.assertIsNotNone(
            MarketplaceReturnRequestService.delivery_time(order)
        )

    def test_an_undelivered_marketplace_order_is_not_eligible(self):
        order = self.delivered_order()
        order.status = MarketplaceOrderStatus.objects.get(name="paid")
        order.save(update_fields=["status", "updated_at"])

        self.assertFalse(MarketplaceReturnRequestService.is_eligible(order))

    def test_an_open_request_closes_the_window(self):
        order = self.delivered_order()
        self.request_return(order)

        self.assertFalse(MarketplaceReturnRequestService.is_eligible(order))
        self.assertEqual(ReturnRequest.objects.count(), 0)

    # ───────────────────────── creating ─────────────────────────

    def test_creating_writes_marketplace_rows_only(self):
        order = self.delivered_order()

        request = self.request_return(order)

        self.assertEqual(MarketplaceReturnRequest.objects.count(), 1)
        self.assertEqual(ReturnRequest.objects.count(), 0)
        self.assertEqual(request.order, order)
        self.assertEqual(request.status, "requested")
        self.assertEqual(request.items.get().quantity, 2)
        self.assertEqual(request.items.get().order_item_id, order.items.get().id)

    def test_returning_more_than_was_sold_is_refused(self):
        order = self.delivered_order()

        with self.assertRaises(MarketplaceReturnRequestService.ValidationError) as ctx:
            self.request_return(order, quantity=3)

        self.assertEqual(list(ctx.exception.errors), ["items"])
        self.assertEqual(MarketplaceReturnRequest.objects.count(), 0)

    # ───────────────────────── admin decisions ─────────────────────────

    def test_admin_actions_follow_the_marketplace_status_graph(self):
        order = self.delivered_order()
        request = self.request_return(order)

        self.assertEqual(
            MarketplaceReturnRequestService.available_admin_actions(
                request.status
            ),
            ["approve", "reject"],
        )

        self.returns.execute_admin_action(
            order.id, request.id, "approve", admin_note="Ok"
        )
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertIsNotNone(request.approved_at)

    def test_a_request_from_another_marketplace_order_is_not_reachable(self):
        order = self.delivered_order()
        request = self.request_return(order)

        with self.assertRaises(MarketplaceReturnRequestService.NotFoundError):
            self.returns.execute_admin_action(order.id + 999, request.id, "approve")

        request.refresh_from_db()
        self.assertEqual(request.status, "requested")

    def test_completion_puts_the_marketplace_cost_layers_back(self):
        order = self.delivered_order(quantity=2)
        request = self.request_return(order)
        self.returns.execute_admin_action(order.id, request.id, "approve")
        self.returns.execute_admin_action(order.id, request.id, "received")

        completed = self.returns.execute_admin_action(
            order.id, request.id, "complete"
        )

        self.assertEqual(completed.status, "completed")
        consumption = InventorySupplyConsumption.objects.get()
        self.assertEqual(consumption.marketplace_order_item, order.items.get())
        self.assertIsNone(consumption.order_item)
        self.assertEqual(consumption.reversed_quantity, 2)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 10)

    def test_the_admin_payload_links_marketplace_evidence(self):
        order = self.delivered_order()
        request = self.request_return(order)

        payload = self.returns.admin_payloads(order)[0]

        self.assertEqual(payload["id"], request.id)
        self.assertEqual(payload["status"], "requested")
        self.assertEqual(payload["evidence"], [])
        self.assertEqual(payload["available_actions"], ["approve", "reject"])
