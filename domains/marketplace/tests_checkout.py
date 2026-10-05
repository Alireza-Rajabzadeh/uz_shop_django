from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from domains.business.models import BusinessProfile
from domains.business_payments.models import (
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentMethod,
)
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.enums.InventoryUnitStateEnum import InventoryUnitStateEnum
from domains.inventory.models import (
    Inventory,
    InventoryUnit,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.marketplace.models import (
    BusinessOffer,
    MarketplaceCart,
    MarketplaceOrder,
    MarketplaceOrderItemReservation,
    MarketplaceOrderStatus,
)
from domains.marketplace.services.order_service import MarketplaceOrderService
from domains.order.models import Order
from domains.vendor.models import Vendor, VendorStatus


class MarketplaceCheckoutFixture(TestCase):
    """Shared marketplace-checkout world: one customer, one seller, one warehouse."""

    def setUp(self):
        MarketplaceOrderSeeder().run()

        self.customer = Customer.objects.create_user(
            phone="09120000701",
            password="password",
            first_name="Marketplace",
            last_name="Checkout",
            customer_code="CUS-MKCO-001",
            status=CustomerStatus.objects.create(name="mkco-active", title="Active"),
        )

        country = Country.objects.create(name="MkCo", code="MX", phone_code="+98")
        state = State.objects.create(name="MkSt", country=country)
        self.city = City.objects.create(name="MkCi", state=state)
        self.warehouse = Warehouse.objects.create(
            code="WH-MKCO",
            name="Marketplace Warehouse",
            city=self.city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-for-mkco"),
        )

        self.category = Category.objects.create(
            name="Marketplace Checkout Category",
            status=CategoryStatus.objects.create(name="mkco-active"),
        )
        self.active_status = ProductStatus.objects.create(name="active")
        self.inactive_status = ProductStatus.objects.create(name="inactive")

        attribute = VariantAttribute.objects.create(name="MkCo Color")
        self.option = VariantOption.objects.create(
            attribute=attribute, name="Black", sku_code="MKCOBLK"
        )

        vendor = Vendor.objects.create(
            phone="+9990000005",
            first_name="MkCo",
            last_name="Vendor",
            national_id="0000000005",
            vendor_code="VEN-MKCO-001",
            status=VendorStatus.objects.create(name="active", title="Active"),
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={
                "vendor": vendor,
                "business_name": "MkCo Business",
                "display_name": "MkCo Business",
            },
        )

        method, _ = BusinessPaymentMethod.objects.get_or_create(
            code="card_to_card",
            defaults={
                "name": "Card to card",
                "fa_name": "کارت به کارت",
                "is_active": True,
            },
        )
        self.channel = BusinessPaymentChannel.objects.create(
            business=self.business,
            code="mkco_manual",
            name="MkCo manual",
            fa_name="درگاه",
            card_number="6104337890123456",
        )
        BusinessPaymentChannelSupportedMethod.objects.create(
            payment_channel=self.channel,
            payment_method=method,
        )

        self.service = MarketplaceOrderService()

    def make_product(self, status=None):
        product = Product.objects.create(
            name="Marketplace Checkout Product", status=status or self.active_status
        )
        product.categories.add(self.category)
        return product

    def make_variant(self, product, price="100.00", available=8, quantity=10,
                     discount_type=None, discount_value=None, offer_active=True):
        variant = ProductVariants.objects.create(
            product=product,
            sku=f"MKCO-PD{product.id}-{self.option.sku_code}",
            combination_key=f"opt:{self.option.id}",
        )
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=variant,
            price=Decimal(price),
            discount_type=discount_type,
            discount_value=discount_value,
            is_active=offer_active,
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

    def filled_cart(self, variant, quantity=1, *, with_address=True):
        cart = MarketplaceCart.objects.create(
            customer=self.customer,
            address_info={"city_name": "MkCi"} if with_address else None,
        )
        cart.items.create(variant=variant, quantity=quantity)
        return cart


class MarketplaceCheckoutTests(MarketplaceCheckoutFixture):
    # ───────────────────────── happy paths ─────────────────────────

    def test_checkout_writes_the_marketplace_tables_and_pins_the_offer(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        cart = self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)

        self.assertIsInstance(order, MarketplaceOrder)
        self.assertEqual(order.business, self.business)
        self.assertEqual(order.status.name, "payment_pending")
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.shipping_original_amount, Decimal("200000.00"))
        self.assertEqual(order.total_amount, Decimal("200.00"))
        self.assertIsNotNone(order.reservation_expires_at)
        self.assertEqual(order.address_info, {"city_name": "MkCi"})

        item = order.items.get()
        self.assertEqual(item.variant, variant)
        self.assertEqual(item.marketplace_offer, offer)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.final_price, Decimal("200.00"))
        self.assertEqual(item.variant_info["product_id"], variant.product_id)

        reservation = item.reservations.get()
        self.assertEqual(reservation.linked_inventory, inventory)
        self.assertIsNone(reservation.linked_unit)
        self.assertEqual(reservation.quantity, 2)

        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 2)
        self.assertEqual(inventory.sellable, 8)

        self.assertEqual(cart.items.count(), 0)

        # The shop flow is untouched by a marketplace checkout.
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_survives_a_later_reprice_of_the_offer(self):
        variant, offer, inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)
        offer.price = Decimal("900.00")
        offer.discount_type = "percentage"
        offer.discount_value = Decimal("50")
        offer.save()
        offer.refresh_from_db()

        order.refresh_from_db()
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.final_price, Decimal("200.00"))
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.total_amount, Decimal("200.00"))
        self.assertEqual(item.discount_amount, Decimal("0.00"))

    def test_checkout_snapshots_discount_values(self):
        variant, _offer, _inventory = self.make_variant(
            self.make_product(),
            price="100.00",
            discount_type="percentage",
            discount_value=Decimal("10"),
        )
        self.filled_cart(variant, quantity=2)

        order = self.service.checkout_from_cart(self.customer)

        item = order.items.get()
        self.assertEqual(item.discount_type, "percentage")
        self.assertEqual(item.discount_value, Decimal("10"))
        self.assertEqual(item.discount_amount, Decimal("20.00"))
        self.assertEqual(item.final_price, Decimal("180.00"))
        self.assertEqual(order.discount_amount, Decimal("20.00"))
        self.assertEqual(order.total_amount, Decimal("180.00"))

    def test_checkout_reserves_serialized_units_individually(self):
        variant, _offer, inventory = self.make_serial_variant(
            self.make_product(), units=3
        )
        self.filled_cart(variant, quantity=2)

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
            self.assertEqual(reservation.linked_inventory, inventory)
            self.assertEqual(
                reservation.linked_unit.state,
                InventoryUnitStateEnum.RESERVED.value,
            )
        self.assertEqual(
            InventoryUnit.objects.filter(
                inventory=inventory,
                state=InventoryUnitStateEnum.RESERVED.value,
            ).count(),
            2,
        )

    # ───────────────────────── validation ─────────────────────────

    def test_a_delivery_address_is_required(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, with_address=False)

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("address", ctx.exception.errors)
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_an_empty_cart_is_rejected(self):
        MarketplaceCart.objects.create(
            customer=self.customer, address_info={"city_name": "MkCi"}
        )

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("cart", ctx.exception.errors)
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_out_of_stock_is_rejected_before_any_row_is_written(self):
        variant, _offer, _inventory = self.make_variant(
            self.make_product(), available=1, quantity=1
        )
        self.filled_cart(variant, quantity=5)

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("items", ctx.exception.errors)
        self.assertEqual(MarketplaceOrder.objects.count(), 0)
        self.assertEqual(MarketplaceOrderItemReservation.objects.count(), 0)

    def test_an_inactive_product_is_rejected(self):
        variant, _offer, _inventory = self.make_variant(
            self.make_product(status=self.inactive_status)
        )
        self.filled_cart(variant)

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("items", ctx.exception.errors)
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_no_active_payment_channel_is_rejected(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant)
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("payment", ctx.exception.errors)
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_a_line_without_an_active_offer_cannot_be_attributed(self):
        variant, offer, _inventory = self.make_variant(
            self.make_product(), offer_active=False
        )
        self.filled_cart(variant)

        with self.assertRaises(MarketplaceOrderService.ValidationError) as ctx:
            self.service.checkout_from_cart(self.customer)

        self.assertIn("items", ctx.exception.errors)
        self.assertIn(variant.sku, str(ctx.exception.errors))
        # Nothing is written: the seller is resolved before the order row.
        self.assertEqual(MarketplaceOrder.objects.count(), 0)
        self.assertEqual(MarketplaceOrderItemReservation.objects.count(), 0)

    # ───────────────────────── atomicity ─────────────────────────

    def test_a_failure_partway_through_leaves_nothing_behind(self):
        variant, _offer, inventory = self.make_variant(self.make_product())
        cart = self.filled_cart(variant, quantity=2)

        with patch.object(
            MarketplaceOrderService,
            "_variant_info_snapshot",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.checkout_from_cart(self.customer)

        self.assertEqual(MarketplaceOrder.objects.count(), 0)
        self.assertEqual(MarketplaceOrderItemReservation.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)
        # The basket survives a failed checkout so the customer can retry.
        self.assertEqual(cart.items.count(), 1)

    def test_pending_status_resolves_from_the_marketplace_vocabulary(self):
        status = self.service._status("payment_pending")

        self.assertIsNotNone(status)
        self.assertIsInstance(status, MarketplaceOrderStatus)
