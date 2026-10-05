from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.management.seeders.order import ORDER_STATUSES, OrderSeeder
from core.management.seeders.payments import PaymentsSeeder
from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.cart.models import Cart
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.enums.InventoryUnitStateEnum import InventoryUnitStateEnum
from domains.inventory.models import (
    Inventory,
    InventoryUnit,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.order.models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderStatus,
)
from domains.order.services import OrderService
from domains.payments.models import (
    PaymentChannel,
    PaymentChannelSupportedMethod,
    PaymentMethod,
)
from domains.vendor.models import Vendor, VendorStatus


class CheckoutFixture(TestCase):
    """Shared shop-checkout world: one customer, one business, one warehouse."""

    def setUp(self):
        OrderSeeder().run()
        PaymentsSeeder().run()

        self.customer = Customer.objects.create_user(
            phone="09120000301",
            password="password",
            first_name="Checkout",
            last_name="Customer",
            customer_code="CUS-CO-001",
            status=CustomerStatus.objects.create(name="checkout-active", title="Active"),
        )

        country = Country.objects.create(name="Co", code="CX", phone_code="+98")
        state = State.objects.create(name="St", country=country)
        self.city = City.objects.create(name="Ci", state=state)
        self.warehouse = Warehouse.objects.create(
            code="WH-CO",
            name="Checkout Warehouse",
            city=self.city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-for-checkout"),
        )

        self.category = Category.objects.create(
            name="Checkout Category",
            status=CategoryStatus.objects.create(name="checkout-active"),
        )
        self.active_status = ProductStatus.objects.create(name="active")
        self.inactive_status = ProductStatus.objects.create(name="inactive")

        attribute = VariantAttribute.objects.create(name="Checkout Color")
        self.option = VariantOption.objects.create(
            attribute=attribute, name="Black", sku_code="COBLK"
        )

        vendor = Vendor.objects.create(
            phone="+9990000003",
            first_name="Checkout",
            last_name="Vendor",
            national_id="0000000003",
            vendor_code="VEN-CO-001",
            status=VendorStatus.objects.create(name="active", title="Active"),
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={
                "vendor": vendor,
                "business_name": "Checkout Business",
                "display_name": "Checkout Business",
            },
        )

        self.channel = PaymentChannel.objects.create(
            code="co_manual",
            name="Co manual",
            fa_name="درگاه",
            card_number="6104337890123456",
        )
        PaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel,
            payment_method=PaymentMethod.objects.get(code="card_to_card"),
        )

        self.service = OrderService()

    def make_product(self, status=None):
        product = Product.objects.create(
            name="Checkout Product", status=status or self.active_status
        )
        product.categories.add(self.category)
        return product

    def make_variant(self, product, price="100.00", available=8, quantity=10,
                     discount_type=None, discount_value=None):
        variant = ProductVariants.objects.create(
            product=product,
            sku=f"CO-PD{product.id}-{self.option.sku_code}",
            combination_key=f"opt:{self.option.id}",
        )
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=variant,
            price=Decimal(price),
            discount_type=discount_type,
            discount_value=discount_value,
        )
        inventory = Inventory.objects.create(
            business=self.business,
            variant=variant,
            warehouse=self.warehouse,
            quantity=quantity,
            sellable=available,
            reserved=0,
            min_stock=0,
        )
        return variant, offer, inventory

    def make_serial_variant(self, product, price="100.00", units=3):
        variant, offer, inventory = self.make_variant(
            product, price=price, available=0, quantity=0
        )
        for _ in range(units):
            InventoryUnit.objects.create(
                inventory=inventory, state=InventoryUnitStateEnum.IN_STOCK.value
            )
        inventory.quantity = units
        inventory.sellable = units
        inventory.save(update_fields=["quantity", "sellable"])
        return variant, offer, inventory

    def filled_cart(self, variant, quantity=1):
        # A customer owns at most one basket, so a fixture that fills twice
        # refills the same one instead of fighting the unique constraint.
        cart, _ = Cart.objects.get_or_create(
            customer=self.customer, defaults={"address_info": {"city_name": "Ci"}}
        )
        cart.items.all().delete()
        cart.items.create(variant=variant, quantity=quantity)
        return cart


class CheckoutTests(CheckoutFixture):
    # ───────────────────────── happy paths ─────────────────────────

    def test_checkout_snapshots_offer_price_and_reserves_normal_stock(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        cart = self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.status.name, "payment_pending")
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.shipping_original_amount, Decimal("200000.00"))
        self.assertEqual(order.shipping_amount, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("200.00"))
        self.assertIsNotNone(order.reservation_expires_at)

        item = order.items.get()
        self.assertEqual(item.variant, variant)
        self.assertEqual(item.sku, variant.sku)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.discount_amount, Decimal("0.00"))
        self.assertEqual(item.final_price, Decimal("200.00"))
        self.assertEqual(item.variant_info["variant_id"], variant.id)
        self.assertEqual(item.variant_info["product_id"], variant.product_id)

        reservation = item.reservations.get()
        self.assertEqual(reservation.linked_inventory, inventory)
        self.assertIsNone(reservation.linked_unit)
        self.assertEqual(reservation.quantity, 2)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 2)
        self.assertEqual(inventory.sellable, 8)

        self.assertEqual(cart.items.count(), 0)

    def test_checkout_snapshots_discount_values(self):
        variant, offer, inventory = self.make_variant(
            self.make_product(),
            price="100.00",
            discount_type="percentage",
            discount_value=Decimal("10"),
        )
        self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)

        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.discount_type, "percentage")
        self.assertEqual(item.discount_value, Decimal("10"))
        self.assertEqual(item.discount_amount, Decimal("20.00"))
        self.assertEqual(item.final_price, Decimal("180.00"))
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.discount_amount, Decimal("20.00"))
        self.assertEqual(order.total_amount, Decimal("180.00"))

    def test_checkout_reserves_serialized_units_individually(self):
        variant, offer, inventory = self.make_serial_variant(self.make_product(), units=3)
        cart = self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)

        reservations = list(order.items.get().reservations.all())
        self.assertEqual(len(reservations), 2)
        self.assertEqual(
            {reservation.linked_unit_id for reservation in reservations},
            set(
                InventoryUnit.objects.filter(inventory=inventory)
                .order_by("id")
                .values_list("id", flat=True)[:2]
            ),
        )
        for reservation in reservations:
            self.assertEqual(reservation.quantity, 1)
            self.assertEqual(reservation.linked_unit.state,
                             InventoryUnitStateEnum.RESERVED.value)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 2)
        self.assertEqual(inventory.sellable, 1)
        self.assertEqual(cart.items.count(), 0)

    # ───────────────────────── validation ─────────────────────────

    def test_checkout_rejects_empty_cart(self):
        Cart.objects.create(customer=self.customer, address_info={"city_name": "Ci"})
        with self.assertRaises(OrderService.ValidationError):
            self.service.checkout_from_cart(self.customer)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_requires_address(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        Cart.objects.create(customer=self.customer).items.create(
            variant=variant, quantity=1
        )
        with self.assertRaises(OrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)
        self.assertIn("address", ctx.exception.errors)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_requires_an_available_payment_channel(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant)
        PaymentChannelSupportedMethod.objects.all().delete()

        with self.assertRaises(OrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)
        self.assertIn("payment", ctx.exception.errors)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_inactive_product(self):
        product = self.make_product()
        variant, offer, inventory = self.make_variant(product)
        self.filled_cart(variant)
        product.status = self.inactive_status
        product.save(update_fields=["status"])

        with self.assertRaises(OrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)
        self.assertIn("items", ctx.exception.errors)
        self.assertEqual(Order.objects.count(), 0)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)

    def test_checkout_rejects_insufficient_stock(self):
        variant, offer, inventory = self.make_variant(self.make_product(), available=1)
        self.filled_cart(variant, quantity=5)

        with self.assertRaises(OrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)
        self.assertIn("items", ctx.exception.errors)

        self.assertEqual(Order.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)

    def test_checkout_rolls_back_everything_when_a_later_step_fails(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        cart = self.filled_cart(variant, quantity=2)

        with patch.object(
            OrderService, "_variant_info_snapshot", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.service.checkout_from_cart(self.customer)

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(OrderItemReservation.objects.count(), 0)
        self.assertEqual(cart.items.count(), 1)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)

    # ───────────────────────── reservation lifecycle ─────────────────────────

    def test_release_reservations_returns_normal_stock(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=3)
        order = self.service.checkout_from_cart(self.customer)

        self.service.release_reservations(order)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)

    def test_release_reservations_frees_serialized_units(self):
        variant, offer, inventory = self.make_serial_variant(self.make_product(), units=3)
        self.filled_cart(variant, quantity=3)
        order = self.service.checkout_from_cart(self.customer)

        self.service.release_reservations(order)

        states = set(
            InventoryUnit.objects.filter(inventory=inventory)
            .values_list("state", flat=True)
        )
        self.assertEqual(states, {InventoryUnitStateEnum.IN_STOCK.value})
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 3)

    def test_consume_reservations_finalizes_normal_stock(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)
        order = self.service.checkout_from_cart(self.customer)

        self.service.consume_reservations(order)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 6)
        self.assertEqual(inventory.quantity, 8)

    def test_consume_reservations_marks_serialized_units_sold(self):
        variant, offer, inventory = self.make_serial_variant(self.make_product(), units=3)
        self.filled_cart(variant, quantity=2)
        order = self.service.checkout_from_cart(self.customer)

        self.service.consume_reservations(order)

        states = sorted(
            InventoryUnit.objects.filter(inventory=inventory)
            .values_list("state", flat=True)
        )
        self.assertEqual(
            states,
            sorted(
                [
                    InventoryUnitStateEnum.SOLD.value,
                    InventoryUnitStateEnum.SOLD.value,
                    InventoryUnitStateEnum.IN_STOCK.value,
                ]
            ),
        )
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 1)

    def test_cancel_action_releases_reservations(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)
        order = self.service.checkout_from_cart(self.customer)

        self.service.execute_action(
            order.id, "cancel", actor="customer", customer=self.customer
        )

        order.refresh_from_db()
        self.assertEqual(order.status.name, "cancelled")
        self.assertIsNone(order.reservation_expires_at)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)

    def test_stale_order_expiry_releases_reservations(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)
        order = self.service.checkout_from_cart(self.customer)
        order.reservation_expires_at = timezone.now() - timezone.timedelta(minutes=1)
        order.save(update_fields=["reservation_expires_at"])

        self.service._expire_if_stale(order)

        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_expired")
        self.assertIsNone(order.reservation_expires_at)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)

    def test_status_seeding_is_available_for_checkout(self):
        self.assertEqual(OrderStatus.objects.count(), len(ORDER_STATUSES))
