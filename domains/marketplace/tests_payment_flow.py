from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from core.management.seeders.order import OrderSeeder
from domains.business_payments.models import (
    BusinessPayment,
    BusinessPaymentMethod,
)
from domains.inventory.models import InventorySupply, InventorySupplyConsumption
from domains.marketplace.models import (
    MarketplaceOrderHistory,
    MarketplaceOrderPayment,
)
from domains.marketplace.services.payment_service import MarketplacePaymentService
from domains.order.models import Order, OrderStatus

from .tests_checkout import MarketplaceCheckoutFixture


class MarketplacePaymentFlowTests(MarketplaceCheckoutFixture):
    """Submitting and reviewing a marketplace payment.

    The workflow itself is inherited from ``BusinessPaymentService``; what
    these pin is that a marketplace payment stays a marketplace payment —
    its rows, its status vocabulary, its audit trail and its hold — and that
    a shop order is simply not visible to it.
    """

    def setUp(self):
        super().setUp()
        self.payments = MarketplacePaymentService()

    def checkout(self, quantity=2):
        variant, _offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        return self.service.checkout_from_cart(self.customer), inventory

    def submit(self, order, **extra):
        kwargs = {
            "payment_method_code": "card_to_card",
            "payment_channel_id": self.channel.id,
        }
        kwargs.update(extra)
        return self.payments.confirm_manual_payment(
            self.business, self.customer, order.id, **kwargs
        )

    # ───────────────────────── submission ─────────────────────────

    def test_submitting_moves_the_order_to_processing(self):
        order, inventory = self.checkout(quantity=2)

        submitted = self.submit(order, ref_number="1234567890")

        self.assertEqual(submitted.status.name, "payment_processing")
        self.assertIsNone(submitted.reservation_expires_at)

        payment = MarketplaceOrderPayment.objects.get()
        self.assertEqual(payment.order, order)
        self.assertEqual(payment.business, self.business)
        self.assertEqual(payment.payment_method.code, "card_to_card")
        self.assertEqual(payment.payment_channel, self.channel)
        self.assertEqual(payment.amount, Decimal("200.00"))
        self.assertEqual(payment.ref_number, "1234567890")
        self.assertEqual(payment.status.name, "pending")

        history = MarketplaceOrderHistory.objects.get()
        self.assertEqual(history.action.code, "submit_payment")
        self.assertEqual(history.user_id, self.customer.pk)

        # The hold survives until review, and no shop row is written.
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 2)
        self.assertEqual(BusinessPayment.objects.count(), 0)

    def test_a_documented_method_requires_a_document(self):
        method = BusinessPaymentMethod.objects.get(code="card_to_card")
        method.requires_documents = True
        method.save(update_fields=["requires_documents"])
        order, _inventory = self.checkout()

        with self.assertRaises(MarketplacePaymentService.ValidationError) as ctx:
            self.submit(order)

        self.assertEqual(list(ctx.exception.errors), ["documents"])
        self.assertEqual(MarketplaceOrderPayment.objects.count(), 0)

    def test_an_order_whose_hold_lapsed_cannot_be_paid(self):
        order, inventory = self.checkout()
        order.reservation_expires_at = timezone.now() - timedelta(minutes=1)
        order.save(update_fields=["reservation_expires_at"])

        with self.assertRaises(MarketplacePaymentService.ValidationError) as ctx:
            self.submit(order)

        self.assertEqual(list(ctx.exception.errors), ["order"])
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(MarketplaceOrderPayment.objects.count(), 0)

    # ───────────────────────── review ─────────────────────────

    def test_approving_pays_the_order_and_attributes_the_cost(self):
        order, inventory = self.checkout(quantity=2)
        self.submit(order)
        payment = MarketplaceOrderPayment.objects.get()
        InventorySupply.objects.create(
            variant=order.items.get().variant,
            warehouse=self.warehouse,
            quantity=10,
            remaining_quantity=10,
            unit_buy_price="40.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            received_at=timezone.make_aware(datetime(2026, 1, 11, 12, 0)),
        )

        reviewed = self.payments.review_payment(
            self.business, payment.id, approve=True
        )

        self.assertEqual(reviewed.status.name, "paid")
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "successful")

        consumption = InventorySupplyConsumption.objects.get()
        self.assertEqual(consumption.marketplace_order_item, order.items.get())
        self.assertIsNone(consumption.order_item)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 6)

        self.assertEqual(
            MarketplaceOrderHistory.objects.filter(action__code="approve_payment")
            .count(),
            1,
        )

    def test_rejecting_marks_it_failed_and_gives_the_stock_back(self):
        order, inventory = self.checkout(quantity=2)
        self.submit(order)
        payment = MarketplaceOrderPayment.objects.get()

        reviewed = self.payments.review_payment(
            self.business, payment.id, approve=False
        )

        self.assertEqual(reviewed.status.name, "payment_failed")
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "failed")
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)
        self.assertEqual(
            MarketplaceOrderHistory.objects.filter(action__code="reject_payment")
            .count(),
            1,
        )

    def test_a_payment_is_reviewed_only_once(self):
        order, _inventory = self.checkout()
        self.submit(order)
        payment = MarketplaceOrderPayment.objects.get()
        self.payments.review_payment(self.business, payment.id, approve=True)

        with self.assertRaises(MarketplacePaymentService.ValidationError) as ctx:
            self.payments.review_payment(self.business, payment.id, approve=True)

        self.assertEqual(list(ctx.exception.errors), ["payment"])

    # ───────────────────────── separation ─────────────────────────

    def test_the_marketplace_payment_list_never_shows_shop_payments(self):
        OrderSeeder().run()
        order, _inventory = self.checkout()
        self.submit(order)
        shop_order = Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "MkCi"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        BusinessPayment.objects.create(
            business=self.business,
            order=shop_order,
            payment_method=BusinessPaymentMethod.objects.get(code="card_to_card"),
            payment_channel=self.channel,
            amount="100.00",
            status=self.payments._status("successful"),
        )

        listed = list(self.payments.list_payments(self.business))

        self.assertEqual([payment.order_id for payment in listed], [order.id])

    def test_a_shop_order_cannot_be_paid_through_this_service(self):
        OrderSeeder().run()
        shop_order = Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "MkCi"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )

        with self.assertRaises(MarketplacePaymentService.NotFoundError):
            self.submit(shop_order)

        self.assertEqual(MarketplaceOrderPayment.objects.count(), 0)
        self.assertEqual(BusinessPayment.objects.count(), 0)
