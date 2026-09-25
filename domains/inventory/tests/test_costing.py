from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariants
from domains.inventory.models import InventorySupply, Warehouse, WarehouseStatus
from domains.inventory.services import InventoryCostService
from domains.location.models import City, Country, State


class InventoryCostingTests(TestCase):
    def setUp(self):
        self.cost_service = InventoryCostService()
        country = Country.objects.create(name="Cost Country", code="CC", phone_code="+1")
        state = State.objects.create(name="Cost State", country=country)
        city = City.objects.create(name="Cost City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-cost-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-COST",
            name="Cost Warehouse",
            city=city,
            address="Cost address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="cost-active")
        product_status = ProductStatus.objects.create(name="cost-pending")
        category = Category.objects.create(name="Cost Category", status=category_status)
        product = Product.objects.create(name="Cost Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            sku="COST-SKU",
            combination_key="cost-sku",
        )
        self.supply = InventorySupply.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=10,
            unit_buy_price="100.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10)),
        )

    def test_landed_cost_summary_uses_original_quantity_and_extra_costs(self):
        self.supply.costs.create(type="shipment", amount="50.00")
        self.supply.costs.create(type="customs", amount="20.00")
        self.supply.costs.create(type="insurance", amount="30.00")

        summary = self.cost_service.get_cost_summary(self.supply)

        self.assertEqual(summary["base_cost_total"], Decimal("1000.00"))
        self.assertEqual(summary["extra_cost_total"], Decimal("100.00"))
        self.assertEqual(summary["landed_cost_total"], Decimal("1100.00"))
        self.assertEqual(summary["landed_unit_cost"], Decimal("110"))

    def test_decimal_values_are_handled_without_float_errors(self):
        supply = InventorySupply.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=3,
            unit_buy_price=Decimal("33.33"),
            supplied_at=timezone.make_aware(datetime(2026, 2, 1)),
        )
        supply.costs.create(type="handling", amount="0.03")

        summary = self.cost_service.get_cost_summary(supply)

        self.assertIsInstance(summary["landed_unit_cost"], Decimal)
        self.assertEqual(summary["base_cost_total"], Decimal("99.99"))
        self.assertEqual(summary["extra_cost_total"], Decimal("0.03"))
        self.assertEqual(summary["landed_cost_total"], Decimal("100.02"))
        self.assertEqual(summary["landed_unit_cost"], Decimal("33.34"))
