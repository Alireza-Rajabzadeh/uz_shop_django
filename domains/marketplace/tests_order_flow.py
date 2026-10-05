from django.db import IntegrityError, transaction
from django.test import TestCase

from core.management.seeders.order import (
    ORDER_ACTIONS,
    ORDER_STATUSES,
    ORDER_STATUS_ACTIONS,
)
from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from domains.business.models import BusinessProfile
from domains.business_payments.models import (
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)
from domains.customer.models import Customer, CustomerStatus
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderAction,
    MarketplaceOrderItem,
    MarketplaceOrderItemReservation,
    MarketplaceOrderPayment,
    MarketplaceOrderStatus,
    MarketplaceOrderStatusAction,
)


class MarketplaceOrderSeederTests(TestCase):
    def test_seeds_the_shop_vocabulary_without_restating_it(self):
        MarketplaceOrderSeeder().run()

        self.assertEqual(MarketplaceOrderStatus.objects.count(), len(ORDER_STATUSES))
        for status_id, expected in ORDER_STATUSES.items():
            status = MarketplaceOrderStatus.objects.get(id=status_id)
            self.assertEqual(
                (status.name, status.fa_name, status.description), expected
            )

        self.assertEqual(MarketplaceOrderAction.objects.count(), len(ORDER_ACTIONS))
        for action_id, expected in ORDER_ACTIONS.items():
            action = MarketplaceOrderAction.objects.get(id=action_id)
            self.assertEqual(
                (
                    action.code,
                    action.name,
                    action.fa_name,
                    action.admin,
                    action.customer,
                    action.set_status_id,
                ),
                expected,
            )

        self.assertEqual(
            MarketplaceOrderStatusAction.objects.count(), len(ORDER_STATUS_ACTIONS)
        )

    def test_seeding_preserves_unrelated_rows(self):
        unrelated = MarketplaceOrderStatus.objects.create(
            id=999,
            name="custom_status",
            fa_name="سفارشی",
            description="Keep me",
        )
        MarketplaceOrderStatus.objects.update_or_create(
            id=100,
            defaults={"name": "old_paid", "fa_name": "Old", "description": "Old"},
        )

        MarketplaceOrderSeeder().run()

        unrelated.refresh_from_db()
        self.assertEqual(unrelated.name, "custom_status")
        self.assertEqual(unrelated.description, "Keep me")
        refreshed = MarketplaceOrderStatus.objects.get(id=100)
        self.assertEqual(refreshed.name, "paid")

    def test_status_action_pair_is_unique(self):
        MarketplaceOrderSeeder().run()

        with self.assertRaises(IntegrityError), transaction.atomic():
            MarketplaceOrderStatusAction.objects.create(
                order_status_id=110, order_action_id=1
            )


class MarketplaceOrderModelTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            phone="09120000401",
            password="password",
            first_name="Marketplace",
            last_name="Customer",
            customer_code="CUS-MK-001",
            status=CustomerStatus.objects.create(name="mkt-active", title="Active"),
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={
                "business_name": "Marketplace Business",
                "display_name": "Marketplace Business",
            },
        )
        MarketplaceOrderSeeder().run()
        self.order = MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Tehran"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        self.method, _ = BusinessPaymentMethod.objects.get_or_create(
            code="card_to_card",
            defaults={"name": "Card to card", "fa_name": "کارت به کارت"},
        )
        self.successful_status, _ = BusinessPaymentStatus.objects.get_or_create(
            name="successful",
            defaults={"title": "پرداخت موفق", "is_active": True},
        )
        self.pending_status, _ = BusinessPaymentStatus.objects.get_or_create(
            name="pending",
            defaults={"title": "در انتظار پرداخت", "is_active": True},
        )

    def make_payment(self, status):
        return MarketplaceOrderPayment.objects.create(
            order=self.order,
            business=self.business,
            payment_method=self.method,
            amount="100.00",
            status=status,
        )

    def test_order_is_scoped_to_its_business(self):
        self.assertEqual(self.order.business_id, self.business.id)
        self.assertIn(self.order, self.business.marketplace_orders.all())

    def test_only_one_successful_payment_per_order(self):
        self.make_payment(self.successful_status)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_payment(self.successful_status)

    def test_several_pending_payments_are_allowed(self):
        self.make_payment(self.pending_status)
        self.make_payment(self.pending_status)
        self.assertEqual(self.order.payments.count(), 2)

    def test_a_second_order_may_have_its_own_successful_payment(self):
        self.make_payment(self.successful_status)
        other = MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Tehran"},
            subtotal="50.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="50.00",
        )
        MarketplaceOrderPayment.objects.create(
            order=other,
            business=self.business,
            payment_method=self.method,
            amount="50.00",
            status=self.successful_status,
        )
        self.assertEqual(self.order.payments.count(), 1)
        self.assertEqual(other.payments.count(), 1)

    def test_order_item_requires_a_positive_quantity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MarketplaceOrderItem.objects.create(
                order=self.order,
                sku="MKT-SKU",
                quantity=0,
                unit_price="100.00",
                final_price="100.00",
            )

    def test_order_item_snapshot_points_at_the_offer_it_was_priced_from(self):
        item = MarketplaceOrderItem.objects.create(
            order=self.order,
            sku="MKT-SKU",
            quantity=2,
            unit_price="100.00",
            discount_amount="0.00",
            final_price="200.00",
        )
        self.assertIsNone(item.marketplace_offer_id)
        self.assertEqual(
            {field.name for field in MarketplaceOrderItem._meta.get_fields()}
            & {"marketplace_offer", "variant"},
            {"marketplace_offer", "variant"},
        )

    def test_reservation_rows_carry_no_legacy_inventory_labels(self):
        """The shop table's generic inventory_type/inventory_id stay shop-only.

        They were read by nothing and would have let a reservation record
        point at stock the reservation service never touched.
        """
        names = {field.name for field in MarketplaceOrderItemReservation._meta.get_fields()}
        self.assertNotIn("inventory_type", names)
        self.assertNotIn("inventory_id", names)
        self.assertIn("linked_inventory", names)
        self.assertIn("linked_unit", names)
