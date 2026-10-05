from datetime import datetime, timedelta

from django.utils import timezone

from domains.inventory.models import InventorySupply, InventorySupplyConsumption
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderHistory,
    MarketplaceOrderStatus,
)

from .tests_checkout import MarketplaceCheckoutFixture


class MarketplaceOrderLifecycleTests(MarketplaceCheckoutFixture):
    """Expiry, actions and audit history on the marketplace tables.

    The machinery is shared with the shop flow through ``BaseOrderService``;
    what these tests pin is that it reaches for the marketplace rows, so a
    status change on a marketplace order cannot end up recorded on a shop
    order.
    """

    def _checked_out(self, quantity=2):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        order = self.service.checkout_from_cart(self.customer)
        return order, inventory

    # ───────────────────────── cancellation ─────────────────────────

    def test_cancelling_releases_the_hold_and_records_marketplace_history(self):
        order, inventory = self._checked_out(quantity=2)

        cancelled = self.service.execute_action(
            order.id, "cancel", actor="customer", customer=self.customer
        )

        self.assertEqual(cancelled.status.name, "cancelled")
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)

        history = MarketplaceOrderHistory.objects.get()
        self.assertEqual(history.order, order)
        self.assertEqual(history.action.code, "cancel")
        self.assertEqual(history.user_id, self.customer.pk)
        self.assertEqual(history.user_model, self.customer._meta.label)
        self.assertIn("status_id", history.after_values)
        self.assertNotEqual(
            history.before_values["status_id"], history.after_values["status_id"]
        )

    def test_cancelling_is_offered_to_the_customer_on_a_pending_order(self):
        order, _inventory = self._checked_out()

        actions = self.service.available_actions(
            order.id, actor="customer", customer=self.customer
        )

        self.assertEqual([action["code"] for action in actions], ["cancel"])
        self.assertEqual(actions[0]["set_status"]["name"], "cancelled")

    def test_an_action_is_scoped_to_its_own_customer(self):
        order, _inventory = self._checked_out()

        with self.assertRaises(self.service.NotFoundError):
            self.service.available_actions(
                order.id, actor="customer", customer=None
            )

    # ───────────────────────── expiry ─────────────────────────

    def test_expiry_releases_the_hold_and_marks_the_order_expired(self):
        order, inventory = self._checked_out(quantity=2)
        order.reservation_expires_at = timezone.now() - timedelta(minutes=1)
        order.save(update_fields=["reservation_expires_at"])

        expired = self.service.expire_orders()

        self.assertEqual([expired_order.pk for expired_order in expired], [order.pk])
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")
        self.assertIsNone(order.reservation_expires_at)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)
        # Expiry releases silently on both flows; it is not a customer or an
        # admin acting, so nothing is attributed to anybody.
        self.assertEqual(MarketplaceOrderHistory.objects.count(), 0)

    def test_expiry_ignores_an_order_that_still_has_time(self):
        order, inventory = self._checked_out()
        order.reservation_expires_at = timezone.now() + timedelta(hours=1)
        order.save(update_fields=["reservation_expires_at"])

        expired = self.service.expire_orders()

        self.assertEqual(expired, [])
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_pending")
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 2)

    # ───────────────────────── payment approval ─────────────────────────

    def test_approving_converts_the_hold_into_a_sale_and_attributes_cost(self):
        order, inventory = self._checked_out(quantity=2)
        supply = InventorySupply.objects.create(
            variant=order.items.get().variant,
            warehouse=self.warehouse,
            quantity=10,
            remaining_quantity=10,
            unit_buy_price="40.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            received_at=timezone.make_aware(datetime(2026, 1, 11, 12, 0)),
        )

        self.service.consume_reservations(order)

        consumption = InventorySupplyConsumption.objects.get()
        self.assertEqual(consumption.marketplace_order_item, order.items.get())
        self.assertIsNone(consumption.order_item)
        self.assertEqual(consumption.quantity, 2)
        supply.refresh_from_db()
        self.assertEqual(supply.remaining_quantity, 8)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 6)
        self.assertEqual(inventory.quantity, 8)

    # ───────────────────────── returns ─────────────────────────

    def test_returns_are_not_offered_while_the_flow_has_none(self):
        order = MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(id=300),
            address_info={"city_name": "MkCi"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )

        actions = self.service.available_actions(
            order.id, actor="customer", customer=self.customer
        )

        # Status 300 carries only request_return, and this flow has no returns
        # service yet, so nobody is shown an action they cannot complete.
        self.assertEqual(actions, [])

        with self.assertRaises(self.service.ValidationError) as ctx:
            self.service.execute_action(
                order.id, "request_return", actor="customer", customer=self.customer
            )
        self.assertEqual(list(ctx.exception.errors), ["action"])
