from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.management.seeders.marketplace_order import MarketplaceOrderSeeder
from core.management.seeders.order import OrderSeeder
from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
)
from domains.customer.models import Customer, CustomerStatus
from domains.inventory.models import (
    Inventory,
    InventorySupply,
    InventorySupplyConsumption,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services.inventory_supply_service import InventorySupplyService
from domains.location.models import City, Country, State
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceOrderItemReservation,
    MarketplaceOrderStatus,
)
from domains.order.models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderStatus,
)


class SupplyConsumptionFixture(TestCase):
    """One supply, one variant, one shop line and one marketplace line.

    The shop and marketplace lines are deliberately built against the same
    variant and the same supply, so a test can only tell them apart by which
    consumption column the service fills.
    """

    def setUp(self):
        OrderSeeder().run()
        MarketplaceOrderSeeder().run()

        country = Country.objects.create(name="Consume Country", code="CN", phone_code="+1")
        state = State.objects.create(name="Consume State", country=country)
        city = City.objects.create(name="Consume City", state=state)
        self.warehouse = Warehouse.objects.create(
            code="WH-CONSUME",
            name="Consume Warehouse",
            city=city,
            address="Consume address",
            lat="0",
            lng="0",
            is_default=True,
            status=WarehouseStatus.objects.create(name="available-consume-tests"),
        )

        category = Category.objects.create(
            name="Consume Category",
            status=CategoryStatus.objects.create(name="consume-active"),
        )
        product = Product.objects.create(
            name="Consume Product",
            status=ProductStatus.objects.create(name="consume-active"),
        )
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            sku="CONSUME-SKU",
            combination_key="consume-sku",
        )

        self.supply = InventorySupply.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=5,
            remaining_quantity=5,
            unit_buy_price="100.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            received_at=timezone.make_aware(datetime(2026, 1, 11, 12, 0)),
        )
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={"business_name": "Consume Business", "display_name": "Consume Business"},
        )
        self.inventory = Inventory.objects.create(
            business=self.business,
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=5,
            sellable=5,
            reserved=0,
            min_stock=0,
        )

        self.customer = Customer.objects.create_user(
            phone="09120000802",
            password="password",
            first_name="Consume",
            last_name="Customer",
            customer_code="CUS-CN-001",
            status=CustomerStatus.objects.create(name="consume-active", title="Active"),
        )
        self.shop_item = self._shop_line()
        self.marketplace_item = self._marketplace_line()
        self.service = InventorySupplyService()

    def _shop_line(self):
        order = Order.objects.create(
            customer=self.customer,
            status=OrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Consume"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        item = OrderItem.objects.create(
            order=order,
            variant=self.variant,
            sku="CONSUME-SKU",
            quantity=2,
            unit_price="100.00",
            final_price="200.00",
        )
        OrderItemReservation.objects.create(
            order_item=item,
            inventory_type="warehouse",
            inventory_id=self.warehouse.id,
            quantity=2,
            linked_inventory=self.inventory,
        )
        return item

    def _marketplace_line(self):
        order = MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(name="payment_pending"),
            address_info={"city_name": "Consume"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="200000.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )
        item = MarketplaceOrderItem.objects.create(
            order=order,
            variant=self.variant,
            sku="CONSUME-SKU",
            quantity=2,
            unit_price="100.00",
            final_price="200.00",
        )
        MarketplaceOrderItemReservation.objects.create(
            order_item=item,
            quantity=2,
            linked_inventory=self.inventory,
        )
        return item


class ConsumeAndReverseTests(SupplyConsumptionFixture):
    """Both flows share one cost-consuming algorithm.

    The marketplace line only changes which column the consumption row
    records; the layer selection, the FIFO walk, the cost arithmetic and the
    reversal are the same code either way.
    """

    def test_a_shop_line_records_cost_against_itself(self):
        self.service.consume_order_item(self.shop_item)

        row = InventorySupplyConsumption.objects.get()
        self.assertEqual(row.order_item, self.shop_item)
        self.assertIsNone(row.marketplace_order_item)
        self.assertEqual(row.quantity, 2)
        self.assertEqual(row.unit_cost, Decimal("100.00"))
        self.assertEqual(row.total_cost, Decimal("200.00"))
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 3)

    def test_a_marketplace_line_records_cost_against_itself(self):
        self.service.consume_order_item(self.marketplace_item)

        row = InventorySupplyConsumption.objects.get()
        self.assertEqual(row.marketplace_order_item, self.marketplace_item)
        self.assertIsNone(row.order_item)
        self.assertEqual(row.quantity, 2)
        self.assertEqual(row.unit_cost, Decimal("100.00"))
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 3)

    def test_the_two_flows_walk_the_same_layers_independently(self):
        self.service.consume_order_item(self.shop_item)
        self.service.consume_order_item(self.marketplace_item)

        self.assertEqual(InventorySupplyConsumption.objects.count(), 2)
        # Only one supply exists, so whichever line consumes second takes the
        # next layer down; neither steals the other's rows.
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 1)

    def test_a_line_consumes_only_once(self):
        self.service.consume_order_item(self.marketplace_item)

        with self.assertRaises(InventorySupplyService.ValidationError) as ctx:
            self.service.consume_order_item(self.marketplace_item)

        self.assertEqual(list(ctx.exception.errors), ["marketplace_order_item"])
        self.assertEqual(InventorySupplyConsumption.objects.count(), 1)

    def test_a_shop_line_still_reports_its_own_field(self):
        self.service.consume_order_item(self.shop_item)

        with self.assertRaises(InventorySupplyService.ValidationError) as ctx:
            self.service.consume_order_item(self.shop_item)

        self.assertEqual(list(ctx.exception.errors), ["order_item"])

    def test_reversing_a_marketplace_line_restores_its_layers(self):
        self.service.consume_order_item(self.marketplace_item)

        reversed_total = self.service.reverse_order_item_consumption(
            self.marketplace_item
        )

        self.assertEqual(reversed_total, 2)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 5)
        row = InventorySupplyConsumption.objects.get()
        self.assertEqual(row.reversed_quantity, 2)

    def test_a_partial_reverse_takes_the_most_recent_layer(self):
        self.service.consume_order_item(self.marketplace_item)

        reversed_total = self.service.reverse_order_item_consumption(
            self.marketplace_item, quantity=1
        )

        self.assertEqual(reversed_total, 1)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 4)
        row = InventorySupplyConsumption.objects.get()
        self.assertEqual(row.reversed_quantity, 1)

    def test_reversing_more_than_was_consumed_is_rejected(self):
        self.service.consume_order_item(self.marketplace_item)

        with self.assertRaises(InventorySupplyService.ValidationError):
            self.service.reverse_order_item_consumption(
                self.marketplace_item, quantity=3
            )

        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 3)

    def test_reversing_both_flows_leaves_each_with_its_own_records(self):
        self.service.consume_order_item(self.shop_item)
        self.service.consume_order_item(self.marketplace_item)

        self.service.reverse_order_item_consumption(self.marketplace_item)

        shop_row, marketplace_row = (
            InventorySupplyConsumption.objects.order_by("id")
        )
        self.assertEqual(shop_row.reversed_quantity, 0)
        self.assertEqual(marketplace_row.reversed_quantity, 2)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 3)

    def test_a_line_with_no_reservation_consumes_nothing(self):
        MarketplaceOrderItemReservation.objects.all().delete()

        consumptions = self.service.consume_order_item(self.marketplace_item)

        self.assertEqual(consumptions, [])
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)
