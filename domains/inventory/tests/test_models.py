from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from core.management.seeders.order import OrderSeeder
from domains.business.models import BusinessProfile
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariants
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.models import (
    InventorySupply,
    InventorySupplyConsumption,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceOrderStatus,
)
from domains.order.models import Order, OrderItem, OrderStatus


class InventorySupplyModelTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name="Supply Country", code="SC", phone_code="+1")
        state = State.objects.create(name="Supply State", country=country)
        city = City.objects.create(name="Supply City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-supply-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-SUPPLY",
            name="Supply Warehouse",
            city=city,
            address="Supply address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="supply-active")
        product_status = ProductStatus.objects.create(name="supply-pending")
        category = Category.objects.create(name="Supply Category", status=category_status)
        product = Product.objects.create(name="Supply Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            sku="SUPPLY-SKU",
            combination_key="supply-sku",
        )

    def make_supply(self, **kwargs):
        defaults = {
            "variant": self.variant,
            "warehouse": self.warehouse,
            "quantity": 5,
            "remaining_quantity": None,
            "unit_buy_price": "100.00",
            "supplied_at": timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
        }
        defaults.update(kwargs)
        return InventorySupply.objects.create(**defaults)

    def test_remaining_quantity_initializes_and_is_preserved_on_update(self):
        supply = self.make_supply(quantity=7)
        self.assertEqual(supply.remaining_quantity, 7)

        supply.quantity = 20
        supply.save(update_fields=["quantity"])
        supply.refresh_from_db()
        self.assertEqual(supply.remaining_quantity, 7)

    def test_zero_quantity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_supply(quantity=0)

    def test_negative_quantity_and_remaining_quantity_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_supply(quantity=-3)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_supply(quantity=5, remaining_quantity=-1)

    def test_variant_deletion_is_protected_while_referenced(self):
        self.make_supply()
        with self.assertRaises(Exception):
            self.variant.delete()

    def test_warehouse_deletion_is_protected_while_referenced(self):
        self.make_supply()
        with self.assertRaises(Exception):
            self.warehouse.delete()


class InventorySupplyConsumptionTargetTests(TestCase):
    """A consumption row belongs to exactly one sale.

    Marketplace lines keep their own reservation and cost rows, so the shop
    ``order_item`` column became optional. "At most one" would let a row
    record cost against nothing; the constraint requires one target.
    """

    def setUp(self):
        OrderSeeder().run()
        MarketplaceOrderSeeder().run()

        country = Country.objects.create(name="Target Country", code="TC", phone_code="+1")
        state = State.objects.create(name="Target State", country=country)
        city = City.objects.create(name="Target City", state=state)
        self.warehouse = Warehouse.objects.create(
            code="WH-TARGET",
            name="Target Warehouse",
            city=city,
            address="Target address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-target-tests"),
        )

        category_status = CategoryStatus.objects.create(name="target-active")
        product_status = ProductStatus.objects.create(name="target-active")
        category = Category.objects.create(name="Target Category", status=category_status)
        product = Product.objects.create(name="Target Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            sku="TARGET-SKU",
            combination_key="target-sku",
        )
        self.supply = InventorySupply.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=5,
            remaining_quantity=5,
            unit_buy_price="100.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
        )

        self.customer = Customer.objects.create_user(
            phone="09120000402",
            password="password",
            first_name="Target",
            last_name="Customer",
            customer_code="CUS-TGT-001",
            status=CustomerStatus.objects.create(name="target-active", title="Active"),
        )
        self.shop_order = Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Target"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        self.shop_item = OrderItem.objects.create(
            order=self.shop_order,
            variant=self.variant,
            sku="TARGET-SKU",
            quantity=2,
            unit_price="100.00",
            final_price="200.00",
        )

        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={"business_name": "Target Business", "display_name": "Target Business"},
        )
        self.marketplace_order = MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Target"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        self.marketplace_item = MarketplaceOrderItem.objects.create(
            order=self.marketplace_order,
            variant=self.variant,
            sku="TARGET-SKU",
            quantity=2,
            unit_price="100.00",
            final_price="200.00",
        )

    def make_consumption(self, **kwargs):
        defaults = {
            "supply": self.supply,
            "quantity": 1,
            # InventorySupplyConsumption.save() derives total_cost from
            # unit_cost, so the cost must arrive as a Decimal, not a string.
            "unit_cost": Decimal("100.00"),
        }
        defaults.update(kwargs)
        return InventorySupplyConsumption.objects.create(**defaults)

    def test_a_shop_item_target_is_accepted(self):
        row = self.make_consumption(order_item=self.shop_item)
        self.assertEqual(row.order_item_id, self.shop_item.id)
        self.assertIsNone(row.marketplace_order_item_id)

    def test_a_marketplace_item_target_is_accepted(self):
        row = self.make_consumption(marketplace_order_item=self.marketplace_item)
        self.assertEqual(row.marketplace_order_item_id, self.marketplace_item.id)
        self.assertIsNone(row.order_item_id)

    def test_both_targets_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_consumption(
                order_item=self.shop_item,
                marketplace_order_item=self.marketplace_item,
            )

    def test_neither_target_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_consumption(
                order_item=None, marketplace_order_item=None
            )

    def test_each_target_has_its_own_per_supply_uniqueness(self):
        self.make_consumption(marketplace_order_item=self.marketplace_item)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_consumption(marketplace_order_item=self.marketplace_item)

        # The shop item still has its own free slot against the same supply.
        self.make_consumption(order_item=self.shop_item)

    def test_shop_and_marketplace_targets_are_independent(self):
        self.make_consumption(order_item=self.shop_item)
        self.make_consumption(marketplace_order_item=self.marketplace_item)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 2)
