from datetime import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariants
from domains.inventory.models import InventorySupply, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State


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
