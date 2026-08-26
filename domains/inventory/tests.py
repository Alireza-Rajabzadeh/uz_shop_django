from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

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
from domains.inventory.models import (
    InventoryStrategy,
    InventorySupply,
    InventorySupplyConsumption,
    InventorySupplyCost,
    SerializedStock,
    SerializedStockStatus,
    VariantPriceHistory,
    VariantPricing,
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)
from domains.inventory.services import (
    InventoryCostService,
    InventoryPricingService,
    InventorySupplyService,
)
from domains.location.models import City, Country, State
from domains.order.models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderStatus,
    ReturnRequest,
    ReturnRequestItem,
)
from domains.order.services import OrderService, ReturnRequestService


class VariantInventoryAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="inventory-admin", password="password")
        self.client.force_authenticate(self.user)
        country = Country.objects.create(name="Inventory Country", code="IC", phone_code="+1")
        state = State.objects.create(name="Inventory State", country=country)
        self.city = City.objects.create(name="Inventory City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-TEST",
            name="Default Test Warehouse",
            city=self.city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        self.in_stock, _ = SerializedStockStatus.objects.update_or_create(
            code="in_stock", defaults={"name": "in_stock"}
        )
        self.sold, _ = SerializedStockStatus.objects.update_or_create(
            code="sold", defaults={"name": "sold"}
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        self.serialized, _ = InventoryStrategy.objects.update_or_create(
            code="serialized", defaults={"name": "Serialized"}
        )
        category_status = CategoryStatus.objects.create(name="inventory-active")
        product_status = ProductStatus.objects.create(name="inventory-pending")
        category = Category.objects.create(name="Inventory Category", status=category_status)
        self.product = Product.objects.create(
            name="Inventory Product", status=product_status
        )
        self.product.categories.add(category)
        self.attribute = VariantAttribute.objects.create(name="Inventory Color")
        self.option_a = VariantOption.objects.create(
            attribute=self.attribute, name="Black", sku_code="INVBLK"
        )
        self.option_b = VariantOption.objects.create(
            attribute=self.attribute, name="White", sku_code="INVWHT"
        )

    def payload(self, *, serialized=False, option=None):
        data = {
            "price": "100.00",
            "inventory_strategy_code": "serialized" if serialized else "normal",
            "selections": [{
                "attribute_id": self.attribute.id,
                "option_id": (option or self.option_a).id,
            }],
        }
        if serialized:
            data["serial_items"] = [
                {"serial_number": "  SN   001  ", "on_sale": True},
                {"serial_number": "SN-002", "on_sale": False},
            ]
        else:
            data["inventory"] = {"quantity": 10, "sellable": 8}
        return data

    def create_variant(self, *, serialized=False, option=None):
        return self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            self.payload(serialized=serialized, option=option),
            format="json",
        )

    def test_normal_create_summary_detail_and_reserved_persistence(self):
        response = self.create_variant()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["total_item_count"], 10)
        self.assertEqual(response.data["data"]["sellable_item_count"], 8)
        self.assertEqual(response.data["data"]["available_item_count"], 8)
        variant = ProductVariants.objects.get()
        stock = WarehouseStock.objects.get(variant=variant, warehouse=self.warehouse)
        stock.reserved = 3
        stock.save(update_fields=["reserved"])

        patch = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"inventory": {"quantity": 12, "sellable": 9}},
            format="json",
        )
        self.assertEqual(patch.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual((stock.quantity, stock.sellable, stock.reserved), (12, 9, 3))
        self.assertEqual(patch.data["data"]["available_item_count"], 6)

        detail = self.client.get(f"/api/inventory/variants/{variant.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["inventory"]["warehouse"]["id"], self.warehouse.id)
        self.assertEqual(detail.data["data"]["inventory"]["reserved"], 3)

    def test_normal_validation_is_atomic_with_catalog_changes(self):
        self.create_variant()
        variant = ProductVariants.objects.get()
        WarehouseStock.objects.filter(variant=variant).update(reserved=5)
        original_price = variant.price
        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {
                "price": "200.00",
                "selections": [{
                    "attribute_id": self.attribute.id,
                    "option_id": self.option_b.id,
                }],
                "inventory": {"quantity": 4, "sellable": 4},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        variant.refresh_from_db()
        self.assertEqual(variant.price, original_price)
        self.assertEqual(variant.selections.get().option, self.option_a)

    def test_serialized_create_normalizes_and_exposes_only_summary_in_lists(self):
        response = self.create_variant(serialized=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["total_item_count"], 2)
        self.assertEqual(response.data["data"]["sellable_item_count"], 1)
        self.assertEqual(response.data["data"]["available_item_count"], 1)
        variant = ProductVariants.objects.get()
        self.assertEqual(
            list(variant.serialized_stocks.values_list("serial_number", flat=True)),
            ["SN 001", "SN-002"],
        )
        listed = self.client.get(f"/api/catalog/products/{self.product.id}/variants")
        self.assertNotIn("serial_items", listed.data["data"][0])
        self.assertNotIn("serialized_stocks", listed.data["data"][0])

        detail = self.client.get(f"/api/inventory/variants/{variant.id}")
        self.assertEqual(detail.data["data"]["serial_items"][0]["status"]["code"], "in_stock")
        self.assertTrue(detail.data["data"]["serial_items"][0]["editable"])

    def test_case_insensitive_duplicate_serial_rolls_back_variant(self):
        payload = self.payload(serialized=True)
        payload["serial_items"][1]["serial_number"] = "sn 001"
        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductVariants.objects.count(), 0)
        self.assertEqual(SerializedStock.objects.count(), 0)

    def test_case_insensitive_duplicate_serial_is_global(self):
        self.assertEqual(self.create_variant(serialized=True).status_code, 201)
        payload = self.payload(serialized=True, option=self.option_b)
        payload["serial_items"][0]["serial_number"] = "sn 001"
        payload["serial_items"][1]["serial_number"] = "SN-OTHER"
        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants", payload, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductVariants.objects.count(), 1)
        self.assertEqual(SerializedStock.objects.count(), 2)

    def test_serialized_snapshot_creates_updates_and_deletes_editable_rows(self):
        self.create_variant(serialized=True)
        variant = ProductVariants.objects.get()
        first, second = list(variant.serialized_stocks.order_by("id"))
        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"serial_items": [
                {"id": first.id, "serial_number": "SN-UPDATED", "on_sale": False},
                {"serial_number": "SN-NEW", "on_sale": True},
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SerializedStock.objects.filter(id=second.id).exists())
        self.assertEqual(
            set(variant.serialized_stocks.values_list("serial_number", flat=True)),
            {"SN-UPDATED", "SN-NEW"},
        )

    def test_serialized_snapshot_can_swap_existing_serial_numbers(self):
        self.create_variant(serialized=True)
        variant = ProductVariants.objects.get()
        first, second = list(variant.serialized_stocks.order_by("id"))
        response = self.client.patch(
            f"/api/inventory/variants/{variant.id}",
            {"serial_items": [
                {"id": first.id, "serial_number": second.serial_number, "on_sale": first.sellable},
                {"id": second.id, "serial_number": first.serial_number, "on_sale": second.sellable},
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.serial_number, second.serial_number), ("SN-002", "SN 001"))

    def test_protected_serial_rows_cannot_be_edited_or_deleted(self):
        self.create_variant(serialized=True)
        variant = ProductVariants.objects.get()
        protected = variant.serialized_stocks.order_by("id").first()
        protected.status = self.sold
        protected.save(update_fields=["status"])
        other = variant.serialized_stocks.order_by("id").last()

        omitted = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"serial_items": [{
                "id": other.id, "serial_number": other.serial_number, "on_sale": other.sellable
            }]},
            format="json",
        )
        edited = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"serial_items": [
                {"id": protected.id, "serial_number": "CHANGED", "on_sale": True},
                {"id": other.id, "serial_number": other.serial_number, "on_sale": other.sellable},
            ]},
            format="json",
        )
        self.assertEqual(omitted.status_code, 400)
        self.assertEqual(edited.status_code, 400)
        protected.refresh_from_db()
        self.assertNotEqual(protected.serial_number, "CHANGED")

    def test_strategy_transition_and_stocked_delete_are_rejected(self):
        self.create_variant()
        variant = ProductVariants.objects.get()
        transition = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"inventory_strategy_code": "serialized", "serial_items": []},
            format="json",
        )
        deletion = self.client.delete(f"/api/catalog/variants/{variant.id}")
        self.assertEqual(transition.status_code, 400)
        self.assertEqual(deletion.status_code, 400)
        self.assertTrue(ProductVariants.objects.filter(id=variant.id).exists())

    def test_empty_strategy_transition_succeeds(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            inventory_strategy=self.normal,
            sku="EMPTY-TRANSITION",
            combination_key="empty-transition",
            price="1.00",
        )
        response = self.client.patch(
            f"/api/catalog/variants/{variant.id}",
            {"inventory_strategy_code": "serialized", "serial_items": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.inventory_strategy, self.serialized)

    def test_form_options_return_both_strategies_and_default_warehouse(self):
        response = self.client.get(
            f"/api/catalog/products/{self.product.id}/variant-form-options"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["code"] for item in response.data["data"]["inventory_strategies"]},
            {"normal", "serialized"},
        )
        self.assertEqual(response.data["data"]["default_warehouse"]["id"], self.warehouse.id)

    def test_inventory_overview_filters_and_stock_only_update(self):
        self.assertEqual(self.create_variant().status_code, 201)
        variant = ProductVariants.objects.get()
        stock = WarehouseStock.objects.get(variant=variant)
        stock.reserved = 2
        stock.min_stock = 7
        stock.save(update_fields=["reserved", "min_stock"])

        listed = self.client.get(
            "/api/inventory/variants",
            {"search": "Inventory Product", "stock_state": "low_stock", "has_reserved": "true"},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["data"]["count"], 1)
        row = listed.data["data"]["results"][0]
        self.assertEqual((row["total"], row["reserved"], row["available"]), (10, 2, 6))
        self.assertTrue(row["low_stock"])

        rejected = self.client.patch(
            f"/api/inventory/variants/{variant.id}",
            {"price": "1.00", "inventory": {"quantity": 12, "sellable": 9, "min_stock": 4}},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        updated = self.client.patch(
            f"/api/inventory/variants/{variant.id}",
            {"inventory": {"quantity": 12, "sellable": 9, "min_stock": 4}},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        stock.refresh_from_db()
        self.assertEqual((stock.quantity, stock.sellable, stock.reserved, stock.min_stock), (12, 9, 2, 4))
        self.assertEqual(updated.data["data"]["sku"], variant.sku)
        self.assertEqual(updated.data["data"]["product"]["id"], self.product.id)

    def test_inventory_custom_permissions_are_enforced(self):
        self.assertEqual(self.create_variant().status_code, 201)
        variant = ProductVariants.objects.get()
        staff = User.objects.create_user(username="inventory-staff", is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/variants").status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_inventory"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/variants").status_code, 200)
        self.assertEqual(
            self.client.patch(
                f"/api/inventory/variants/{variant.id}",
                {"inventory": {"quantity": 10, "sellable": 8, "min_stock": 0}},
                format="json",
            ).status_code,
            403,
        )
        staff.user_permissions.add(Permission.objects.get(codename="adjust_stock"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.patch(
                f"/api/inventory/variants/{variant.id}",
                {"inventory": {"quantity": 10, "sellable": 8, "min_stock": 0}},
                format="json",
            ).status_code,
            200,
        )

        adjust_only = User.objects.create_user(username="inventory-adjuster", is_staff=True)
        adjust_only.user_permissions.add(Permission.objects.get(codename="adjust_stock"))
        self.client.force_authenticate(User.objects.get(pk=adjust_only.pk))
        self.assertEqual(
            self.client.patch(
                f"/api/inventory/variants/{variant.id}",
                {"inventory": {"quantity": 10, "sellable": 8, "min_stock": 0}},
                format="json",
            ).status_code,
            403,
        )

    def test_warehouse_crud_default_rules_and_protected_stock(self):
        payload = {
            "name": "Second Warehouse",
            "city": self.city.id,
            "address": "Second address",
            "lat": "35.700000",
            "lng": "51.400000",
            "phone_numbers": ["02100000000"],
            "postal_code": "12345",
            "status": self.warehouse_status.id,
        }
        created = self.client.post("/api/inventory/warehouses", payload, format="json")
        self.assertEqual(created.status_code, 201)
        second_id = created.data["data"]["id"]
        self.assertFalse(created.data["data"]["is_default"])
        self.assertTrue(created.data["data"]["code"].startswith("WH-"))
        self.assertEqual(self.client.delete(f"/api/inventory/warehouses/{self.warehouse.id}").status_code, 400)

        switched = self.client.patch(
            f"/api/inventory/warehouses/{second_id}", {"is_default": True}, format="json"
        )
        self.assertEqual(switched.status_code, 200)
        self.warehouse.refresh_from_db()
        self.assertFalse(self.warehouse.is_default)

        self.assertEqual(self.create_variant().status_code, 201)
        blocked_switch = self.client.patch(
            f"/api/inventory/warehouses/{self.warehouse.id}",
            {"is_default": True},
            format="json",
        )
        self.assertEqual(blocked_switch.status_code, 400)
        protected = self.client.delete(f"/api/inventory/warehouses/{second_id}")
        self.assertEqual(protected.status_code, 400)
        self.assertIn("default", str(protected.data).lower())

    def test_only_default_warehouse_cannot_be_deleted(self):
        response = self.client.delete(f"/api/inventory/warehouses/{self.warehouse.id}")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Warehouse.objects.filter(pk=self.warehouse.id, is_default=True).exists())


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
        self.other_warehouse = Warehouse.objects.create(
            code="WH-SUPPLY-2",
            name="Second Supply Warehouse",
            city=city,
            address="Second supply address",
            lat="1",
            lng="1",
            status=warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        category_status = CategoryStatus.objects.create(name="supply-active")
        product_status = ProductStatus.objects.create(name="supply-pending")
        category = Category.objects.create(name="Supply Category", status=category_status)
        product = Product.objects.create(name="Supply Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="SUPPLY-SKU",
            combination_key="supply-sku",
            price="10.00",
        )

    def supply(self, *, variant=None, warehouse=None, quantity=5, remaining_quantity=None,
               unit_buy_price="100.00", supplied_at=None, **extra):
        return InventorySupply.objects.create(
            variant=variant or self.variant,
            warehouse=warehouse or self.warehouse,
            quantity=quantity,
            remaining_quantity=remaining_quantity,
            unit_buy_price=unit_buy_price,
            supplied_at=supplied_at or timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            **extra,
        )

    def test_create_initializes_remaining_quantity_to_quantity(self):
        supply = self.supply(quantity=7)
        self.assertIsNotNone(supply.id)
        self.assertEqual(supply.remaining_quantity, 7)
        supply.refresh_from_db()
        self.assertEqual(supply.remaining_quantity, 7)

    def test_update_does_not_reinitialize_remaining_quantity(self):
        supply = self.supply(quantity=7)
        supply.quantity = 20
        supply.save(update_fields=["quantity"])
        supply.refresh_from_db()
        self.assertEqual(supply.remaining_quantity, 7)

    def test_zero_quantity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supply(quantity=0)

    def test_negative_quantity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supply(quantity=-3)

    def test_negative_remaining_quantity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supply(quantity=5, remaining_quantity=-1)

    def test_remaining_quantity_above_quantity_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supply(quantity=5, remaining_quantity=6)

    def test_negative_unit_buy_price_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supply(unit_buy_price="-0.01")

    def test_multiple_supplies_per_variant_are_allowed(self):
        first = self.supply(supplied_at=timezone.make_aware(datetime(2026, 1, 1)))
        second = self.supply(supplied_at=timezone.make_aware(datetime(2026, 2, 1)))
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.variant.inventory_supplies.count(), 2)

    def test_multiple_supplies_per_variant_and_warehouse_are_allowed(self):
        self.supply(warehouse=self.warehouse, supplied_at=timezone.make_aware(datetime(2026, 1, 1)))
        self.supply(warehouse=self.warehouse, supplied_at=timezone.make_aware(datetime(2026, 2, 1)))
        self.assertEqual(
            InventorySupply.objects.filter(variant=self.variant, warehouse=self.warehouse).count(),
            2,
        )

    def test_default_ordering_is_supplied_then_id(self):
        older = self.supply(supplied_at=timezone.make_aware(datetime(2026, 1, 1)))
        newer = self.supply(supplied_at=timezone.make_aware(datetime(2026, 3, 1)))
        middle_a = self.supply(supplied_at=timezone.make_aware(datetime(2026, 2, 1)))
        middle_b = self.supply(supplied_at=timezone.make_aware(datetime(2026, 2, 1)))
        self.assertEqual(
            list(InventorySupply.objects.all()),
            [older, middle_a, middle_b, newer],
        )

    def test_variant_deletion_is_protected_while_referenced(self):
        self.supply()
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.variant.delete()

    def test_warehouse_deletion_is_protected_while_referenced(self):
        self.supply(warehouse=self.other_warehouse)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.other_warehouse.delete()


class InventorySupplyCostTests(TestCase):
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
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        category_status = CategoryStatus.objects.create(name="cost-active")
        product_status = ProductStatus.objects.create(name="cost-pending")
        category = Category.objects.create(name="Cost Category", status=category_status)
        product = Product.objects.create(name="Cost Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="COST-SKU",
            combination_key="cost-sku",
            price="10.00",
        )
        self.supply = InventorySupply.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=10,
            unit_buy_price="100.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10)),
        )

    def cost(self, *, supply=None, type_code="shipment", amount="50.00", description=""):
        return InventorySupplyCost.objects.create(
            supply=supply or self.supply,
            type=type_code,
            amount=amount,
            description=description,
        )

    def test_cost_can_be_created_for_supply(self):
        cost = self.cost(type_code="customs", amount="30.00", description="Customs fee")
        self.assertIsNotNone(cost.id)
        self.assertEqual(cost.supply_id, self.supply.id)
        self.assertEqual(self.supply.costs.count(), 1)

    def test_multiple_costs_can_belong_to_one_supply(self):
        first = self.cost(type_code="shipment", amount="50.00")
        second = self.cost(type_code="insurance", amount="10.00")
        third = self.cost(type_code="tax", amount="5.00")
        self.assertEqual(
            set(self.supply.costs.values_list("id", flat=True)),
            {first.id, second.id, third.id},
        )

    def test_multiple_costs_of_same_type_are_allowed(self):
        first = self.cost(type_code="shipment", amount="100000.00")
        second = self.cost(type_code="shipment", amount="20000.00")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(
            self.supply.costs.filter(type="shipment").count(),
            2,
        )

    def test_zero_amount_is_allowed(self):
        cost = self.cost(type_code="other", amount="0.00")
        cost.refresh_from_db()
        self.assertEqual(cost.amount, Decimal("0.00"))

    def test_negative_amount_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.cost(amount="-1.00")

    def test_deleting_supply_deletes_cost_records(self):
        cost = self.cost()
        self.supply.delete()
        self.assertFalse(InventorySupplyCost.objects.filter(id=cost.id).exists())

    def test_deleting_cost_does_not_delete_supply(self):
        cost = self.cost()
        cost.delete()
        self.assertTrue(InventorySupply.objects.filter(id=self.supply.id).exists())

    def test_landed_cost_calculations_use_original_quantity(self):
        self.cost(type_code="shipment", amount="50.00")
        self.cost(type_code="customs", amount="20.00")
        self.cost(type_code="insurance", amount="30.00")
        summary = self.cost_service.get_cost_summary(self.supply)
        self.assertEqual(summary["base_cost_total"], Decimal("1000.00"))
        self.assertEqual(summary["extra_cost_total"], Decimal("100.00"))
        self.assertEqual(summary["landed_cost_total"], Decimal("1100.00"))
        self.assertEqual(summary["landed_unit_cost"], Decimal("110"))

    def test_supply_without_costs_has_zero_extra_and_base_landed_total(self):
        summary = self.cost_service.get_cost_summary(self.supply)
        self.assertEqual(summary["extra_cost_total"], Decimal("0"))
        self.assertEqual(summary["base_cost_total"], Decimal("1000.00"))
        self.assertEqual(summary["landed_cost_total"], Decimal("1000.00"))
        self.assertEqual(summary["landed_unit_cost"], Decimal("100"))

    def test_duplicate_type_rows_are_all_included_in_extra_total(self):
        self.cost(type_code="shipment", amount="100.00")
        self.cost(type_code="shipment", amount="20.00")
        summary = self.cost_service.get_cost_summary(self.supply)
        self.assertEqual(summary["extra_cost_total"], Decimal("120.00"))
        self.assertEqual(summary["landed_cost_total"], Decimal("1120.00"))

    def test_remaining_quantity_does_not_change_landed_unit_cost(self):
        self.cost(type_code="shipment", amount="50.00")
        self.cost(type_code="customs", amount="20.00")
        self.cost(type_code="insurance", amount="30.00")
        self.supply.remaining_quantity = 2
        self.supply.save(update_fields=["remaining_quantity"])
        summary = self.cost_service.get_cost_summary(self.supply)
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
        self.cost(supply=supply, type_code="handling", amount="0.03")
        summary = self.cost_service.get_cost_summary(supply)
        self.assertIsInstance(summary["landed_unit_cost"], Decimal)
        self.assertEqual(summary["base_cost_total"], Decimal("99.99"))
        self.assertEqual(summary["extra_cost_total"], Decimal("0.03"))
        self.assertEqual(summary["landed_cost_total"], Decimal("100.02"))
        self.assertEqual(summary["landed_unit_cost"], Decimal("33.34"))


class InventorySupplyAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="supply-admin", password="password")
        self.client.force_authenticate(self.user)
        country = Country.objects.create(name="Supply API Country", code="SA", phone_code="+1")
        state = State.objects.create(name="Supply API State", country=country)
        self.city = City.objects.create(name="Supply API City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-supply-api")
        self.warehouse = Warehouse.objects.create(
            code="WH-SUPPLY-API",
            name="Supply API Warehouse",
            city=self.city,
            address="Supply API address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        self.second_warehouse = Warehouse.objects.create(
            code="WH-SUPPLY-API-2",
            name="Second Supply API Warehouse",
            city=self.city,
            address="Second supply API address",
            lat="1",
            lng="1",
            status=warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        category_status = CategoryStatus.objects.create(name="supply-api-active")
        product_status = ProductStatus.objects.create(name="supply-api-pending")
        category = Category.objects.create(name="Supply API Category", status=category_status)
        product = Product.objects.create(name="Supply API Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="SUPPLY-API-SKU",
            combination_key="supply-api-sku",
            price="10.00",
        )
        self.serialized_strategy, _ = InventoryStrategy.objects.update_or_create(
            code="serialized", defaults={"name": "Serialized"}
        )
        self.serialized_variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.serialized_strategy,
            sku="SUPPLY-API-SER",
            combination_key="supply-api-ser",
            price="10.00",
        )
        self.in_stock_status, _ = SerializedStockStatus.objects.update_or_create(
            code="in_stock", defaults={"name": "in_stock"}
        )

    def create_serialized_supply(self, *, quantity=2, **overrides):
        return self.client.post(
            "/api/inventory/supplies",
            self.payload(variant_id=self.serialized_variant.id, quantity=quantity, **overrides),
            format="json",
        )

    def payload(self, **overrides):
        data = {
            "variant_id": self.variant.id,
            "warehouse_id": self.warehouse.id,
            "quantity": 10,
            "unit_buy_price": "100.00",
            "supplied_at": "2026-08-26T10:00:00Z",
            "reference_number": "PO-100",
            "invoice_number": "INV-500",
            "notes": "First shipment",
            "costs": [
                {"type": "shipment", "amount": "50.00", "description": "Freight"},
                {"type": "customs", "amount": "20.00"},
                {"type": "insurance", "amount": "30.00"},
            ],
        }
        data.update(overrides)
        return data

    def create_supply(self, **overrides):
        return self.client.post("/api/inventory/supplies", self.payload(**overrides), format="json")

    def stock_row(self):
        stock = WarehouseStock.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=5,
            sellable=5,
            reserved=1,
            min_stock=2,
        )
        return stock

    def test_authentication_and_permissions_are_required(self):
        self.client.force_authenticate(None)
        self.assertIn(
            self.client.get("/api/inventory/supplies").status_code, (401, 403)
        )
        staff = User.objects.create_user(username="supply-staff", is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/supplies").status_code, 403)
        self.assertEqual(self.create_supply().status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_inventory"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/supplies").status_code, 200)
        self.assertEqual(self.create_supply().status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="adjust_stock"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.create_supply().status_code, 201)

    def test_list_is_paginated_and_returns_calculated_costs(self):
        self.create_supply()
        response = self.client.get("/api/inventory/supplies")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, data)
        row = data["results"][0]
        self.assertEqual(row["variant"]["sku"], "SUPPLY-API-SKU")
        self.assertEqual(row["warehouse"]["code"], "WH-SUPPLY-API")
        self.assertEqual(row["quantity"], 10)
        self.assertEqual(row["remaining_quantity"], 10)
        self.assertEqual(row["base_cost_total"], "1000.00")
        self.assertEqual(row["extra_cost_total"], "100.00")
        self.assertEqual(row["landed_cost_total"], "1100.00")
        self.assertEqual(Decimal(row["landed_unit_cost"]), Decimal("110"))

    def test_detail_returns_notes_and_cost_rows_with_totals(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        response = self.client.get(f"/api/inventory/supplies/{supply_id}")
        self.assertEqual(response.status_code, 200)
        detail = response.data["data"]
        self.assertEqual(detail["notes"], "First shipment")
        self.assertEqual(len(detail["costs"]), 3)
        self.assertEqual(detail["costs"][0]["type"], "shipment")
        self.assertEqual(detail["costs"][0]["amount"], "50.00")
        self.assertEqual(detail["landed_cost_total"], "1100.00")

        missing = self.client.get("/api/inventory/supplies/999999")
        self.assertEqual(missing.status_code, 404)

    def test_search_matches_sku_product_reference_and_invoice(self):
        self.create_supply()
        other_product = Product.objects.create(
            name="Searchable Gadget", status=ProductStatus.objects.first()
        )
        other_variant = ProductVariants.objects.create(
            product=other_product,
            inventory_strategy=self.normal,
            sku="OTHER-SKU",
            combination_key="other-sku",
            price="5.00",
        )
        self.client.post(
            "/api/inventory/supplies",
            self.payload(variant_id=other_variant.id, reference_number="", invoice_number=""),
            format="json",
        )
        by_sku = self.client.get("/api/inventory/supplies", {"search": "OTHER-SKU"})
        self.assertEqual(by_sku.data["data"]["count"], 1)
        self.assertEqual(by_sku.data["data"]["results"][0]["variant"]["id"], other_variant.id)
        by_product = self.client.get("/api/inventory/supplies", {"search": "searchable gadget"})
        self.assertEqual(by_product.data["data"]["count"], 1)
        by_reference = self.client.get("/api/inventory/supplies", {"search": "PO-100"})
        self.assertEqual(by_reference.data["data"]["count"], 1)
        self.assertEqual(by_reference.data["data"]["results"][0]["variant"]["sku"], "SUPPLY-API-SKU")
        by_invoice = self.client.get("/api/inventory/supplies", {"search": "inv-500"})
        self.assertEqual(by_invoice.data["data"]["count"], 1)

    def test_variant_and_warehouse_filters_work(self):
        other_product = Product.objects.create(
            name="Filter Product", status=ProductStatus.objects.first()
        )
        other_variant = ProductVariants.objects.create(
            product=other_product,
            inventory_strategy=self.normal,
            sku="FILTER-SKU",
            combination_key="filter-sku",
            price="5.00",
        )
        self.create_supply()
        self.create_supply(variant_id=other_variant.id, warehouse_id=self.second_warehouse.id)
        by_variant = self.client.get("/api/inventory/supplies", {"variant_id": other_variant.id})
        self.assertEqual(by_variant.data["data"]["count"], 1)
        self.assertEqual(by_variant.data["data"]["results"][0]["variant"]["sku"], "FILTER-SKU")
        by_warehouse = self.client.get(
            "/api/inventory/supplies", {"warehouse_id": self.second_warehouse.id}
        )
        self.assertEqual(by_warehouse.data["data"]["count"], 1)
        both = self.client.get(
            "/api/inventory/supplies",
            {"variant_id": self.variant.id, "warehouse_id": self.warehouse.id},
        )
        self.assertEqual(both.data["data"]["count"], 1)

    def test_date_filters_bound_supplied_at(self):
        old = self.create_supply(supplied_at="2026-01-05T00:00:00Z")
        new = self.create_supply(supplied_at="2026-03-15T00:00:00Z")
        self.assertEqual(old.status_code, 201)
        self.assertEqual(new.status_code, 201)
        february_onward = self.client.get(
            "/api/inventory/supplies", {"date_from": "2026-02-01T00:00:00Z"}
        )
        results = february_onward.data["data"]["results"]
        self.assertEqual(february_onward.data["data"]["count"], 1)
        self.assertTrue(results[0]["supplied_at"].startswith("2026-03-15"))
        through_february = self.client.get(
            "/api/inventory/supplies", {"date_to": "2026-02-28T23:59:59Z"}
        )
        results = through_february.data["data"]["results"]
        self.assertEqual(through_february.data["data"]["count"], 1)
        self.assertTrue(results[0]["supplied_at"].startswith("2026-01-05"))

    def test_has_remaining_filter(self):
        supplied = self.create_supply()
        supply_id = supplied.data["data"]["id"]
        InventorySupply.objects.filter(id=supply_id).update(remaining_quantity=0)
        remaining_only = self.client.get("/api/inventory/supplies", {"has_remaining": "true"})
        self.assertEqual(remaining_only.data["data"]["count"], 0)
        consumed_only = self.client.get("/api/inventory/supplies", {"has_remaining": "false"})
        self.assertEqual(consumed_only.data["data"]["count"], 1)
        self.assertEqual(consumed_only.data["data"]["results"][0]["remaining_quantity"], 0)

    def test_ordering_allowlist_with_safe_fallback(self):
        cheap = self.create_supply(unit_buy_price="10.00")
        expensive = self.create_supply(unit_buy_price="500.00")
        self.assertEqual(cheap.status_code, 201)
        self.assertEqual(expensive.status_code, 201)
        default_ordered = self.client.get("/api/inventory/supplies")
        rows = default_ordered.data["data"]["results"]
        self.assertGreaterEqual(
            rows[0]["supplied_at"],
            rows[-1]["supplied_at"],
        )
        by_price = self.client.get("/api/inventory/supplies", {"ordering": "-unit_buy_price"})
        prices = [Decimal(row["unit_buy_price"]) for row in by_price.data["data"]["results"]]
        self.assertEqual(prices, sorted(prices, reverse=True))
        unsupported = self.client.get("/api/inventory/supplies", {"ordering": "hacker_field"})
        self.assertEqual(unsupported.status_code, 200)
        fallback_prices = [
            Decimal(row["unit_buy_price"]) for row in unsupported.data["data"]["results"]
        ]
        self.assertEqual(fallback_prices, prices)

    def test_create_returns_remaining_quantity_and_correct_totals(self):
        created = self.create_supply(quantity=20, unit_buy_price="100000.00")
        self.assertEqual(created.status_code, 201)
        detail = created.data["data"]
        supply_id = detail["id"]
        self.assertEqual(detail["quantity"], 20)
        self.assertEqual(detail["remaining_quantity"], 20)
        self.assertEqual(len(detail["costs"]), 3)
        self.assertEqual(detail["base_cost_total"], "2000000.00")
        self.assertEqual(detail["extra_cost_total"], "100.00")
        self.assertEqual(detail["landed_cost_total"], "2000100.00")
        stored = InventorySupply.objects.get(id=supply_id)
        self.assertEqual(stored.remaining_quantity, 20)
        self.assertEqual(stored.costs.count(), 3)

    def test_invalid_or_negative_costs_are_rejected_atomically(self):
        invalid_type = self.create_supply(costs=[
            {"type": "shipment", "amount": "50.00"},
            {"type": "delivery_magic", "amount": "10.00"},
        ])
        self.assertEqual(invalid_type.status_code, 400)
        negative = self.create_supply(costs=[{"type": "tax", "amount": "-1.00"}])
        self.assertEqual(negative.status_code, 400)
        valid_part = self.create_supply(costs=[
            {"type": "shipment", "amount": "50.00"},
            {"type": "customs", "amount": "-5.00"},
        ])
        self.assertEqual(valid_part.status_code, 400)
        self.assertEqual(InventorySupply.objects.count(), 0)
        self.assertEqual(InventorySupplyCost.objects.count(), 0)

    def test_unknown_fields_and_forbidden_inputs_are_rejected(self):
        unknown = self.create_supply(some_random_field=True)
        self.assertEqual(unknown.status_code, 400)
        with_remaining = self.create_supply(remaining_quantity=5)
        self.assertEqual(with_remaining.status_code, 400)
        calculated = self.create_supply(
            base_cost_total="1",
            extra_cost_total="1",
            landed_cost_total="1",
            landed_unit_cost="1",
        )
        self.assertEqual(calculated.status_code, 400)
        self.assertEqual(InventorySupply.objects.count(), 0)

    def test_service_level_cost_validation_rolls_back_supply(self):
        service = InventorySupplyService()
        variant = self.variant
        with self.assertRaises(service.ValidationError), transaction.atomic():
            service.create_supply(
                variant=variant,
                warehouse=self.warehouse,
                quantity=10,
                unit_buy_price=Decimal("100.00"),
                supplied_at=timezone.make_aware(datetime(2026, 8, 26)),
                costs=[{"type": "shipment", "amount": Decimal("50.00")},
                       {"type": "delivery_magic", "amount": Decimal("1.00")}],
            )
        self.assertEqual(InventorySupply.objects.count(), 0)
        self.assertEqual(InventorySupplyCost.objects.count(), 0)

    def test_patch_updates_metadata_and_price_with_new_totals(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        updated = self.client.patch(
            f"/api/inventory/supplies/{supply_id}",
            {
                "reference_number": "PO-UPDATED",
                "invoice_number": "INV-UPDATED",
                "notes": "Updated notes",
                "warehouse_id": self.second_warehouse.id,
                "unit_buy_price": "200.00",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        detail = updated.data["data"]
        self.assertEqual(detail["reference_number"], "PO-UPDATED")
        self.assertEqual(detail["invoice_number"], "INV-UPDATED")
        self.assertEqual(detail["notes"], "Updated notes")
        self.assertEqual(detail["warehouse"]["id"], self.second_warehouse.id)
        self.assertEqual(detail["base_cost_total"], "2000.00")
        self.assertEqual(detail["landed_cost_total"], "2100.00")
        self.assertEqual(Decimal(detail["landed_unit_cost"]), Decimal("210"))
        stored = InventorySupply.objects.get(id=supply_id)
        self.assertEqual(stored.remaining_quantity, 10)

    def test_patch_replaces_full_cost_snapshot(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        updated = self.client.patch(
            f"/api/inventory/supplies/{supply_id}",
            {
                "costs": [
                    {"type": "shipment", "amount": "70.00"},
                    {"type": "handling", "amount": "5.00"},
                ]
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        detail = updated.data["data"]
        self.assertEqual(len(detail["costs"]), 2)
        self.assertEqual({row["type"] for row in detail["costs"]}, {"shipment", "handling"})
        self.assertEqual(detail["extra_cost_total"], "75.00")
        self.assertEqual(detail["landed_cost_total"], "1075.00")

    def test_remaining_quantity_cannot_be_patched_directly(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        rejected = self.client.patch(
            f"/api/inventory/supplies/{supply_id}", {"remaining_quantity": 4}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        stored = InventorySupply.objects.get(id=supply_id)
        self.assertEqual(stored.remaining_quantity, 10)

    def test_quantity_change_updates_remaining_when_untouched(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        updated = self.client.patch(
            f"/api/inventory/supplies/{supply_id}", {"quantity": 25}, format="json"
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["data"]["quantity"], 25)
        self.assertEqual(updated.data["data"]["remaining_quantity"], 25)
        self.assertEqual(updated.data["data"]["base_cost_total"], "2500.00")

    def test_quantity_change_rejected_after_consumption_started(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        InventorySupply.objects.filter(id=supply_id).update(remaining_quantity=2)
        rejected = self.client.patch(
            f"/api/inventory/supplies/{supply_id}", {"quantity": 25}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        stored = InventorySupply.objects.get(id=supply_id)
        self.assertEqual((stored.quantity, stored.remaining_quantity), (10, 2))

    def test_delete_rules_and_cascade(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        self.assertEqual(InventorySupplyCost.objects.filter(supply_id=supply_id).count(), 3)
        deleted = self.client.delete(f"/api/inventory/supplies/{supply_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(InventorySupply.objects.filter(id=supply_id).exists())
        self.assertEqual(InventorySupplyCost.objects.filter(supply_id=supply_id).count(), 0)

        consumed = self.create_supply()
        consumed_id = consumed.data["data"]["id"]
        InventorySupply.objects.filter(id=consumed_id).update(remaining_quantity=4)
        rejected = self.client.delete(f"/api/inventory/supplies/{consumed_id}")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("consumed", str(rejected.data))
        self.assertTrue(InventorySupply.objects.filter(id=consumed_id).exists())

    def test_supply_lifecycle_never_touches_physical_inventory(self):
        stock = self.stock_row()
        snapshot = (
            stock.quantity,
            stock.sellable,
            stock.reserved,
            stock.min_stock,
        )
        created = self.create_supply()
        self.assertEqual(created.status_code, 201)
        supply_id = created.data["data"]["id"]

        patched = self.client.patch(
            f"/api/inventory/supplies/{supply_id}",
            {"quantity": 30, "unit_buy_price": "120.00"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        deleted = self.client.delete(f"/api/inventory/supplies/{supply_id}")
        self.assertEqual(deleted.status_code, 200)

        stock.refresh_from_db()
        self.assertEqual(
            (stock.quantity, stock.sellable, stock.reserved, stock.min_stock),
            snapshot,
        )
        self.assertEqual(WarehouseStock.objects.count(), 1)
        self.assertEqual(SerializedStock.objects.count(), 0)

    def test_supply_cost_types_endpoint_lists_enum_options(self):
        response = self.client.get("/api/inventory/supply-cost-types")
        self.assertEqual(response.status_code, 200)
        options = response.data["data"]
        self.assertEqual(
            [(item["code"], item["name"]) for item in options],
            [
                ("shipment", "Shipment"),
                ("customs", "Customs"),
                ("insurance", "Insurance"),
                ("tax", "Tax"),
                ("commission", "Commission"),
                ("handling", "Handling"),
                ("storage", "Storage"),
                ("other", "Other"),
            ],
        )

    def test_receive_normal_supply_adds_delta_and_sets_received(self):
        stock = self.stock_row()
        created = self.create_supply(quantity=10)
        supply_id = created.data["data"]["id"]
        self.assertIsNone(created.data["data"]["received_at"])
        self.assertFalse(created.data["data"]["is_received"])

        response = self.client.post(f"/api/inventory/supplies/{supply_id}/receive")
        self.assertEqual(response.status_code, 200)
        detail = response.data["data"]
        self.assertIsNotNone(detail["received_at"])
        self.assertTrue(detail["is_received"])

        stock.refresh_from_db()
        self.assertEqual((stock.quantity, stock.sellable, stock.reserved, stock.min_stock), (15, 15, 1, 2))
        supply = InventorySupply.objects.get(id=supply_id)
        self.assertEqual(supply.remaining_quantity, 10)

    def test_receive_creates_missing_warehouse_stock_row(self):
        created = self.create_supply(quantity=7)
        supply_id = created.data["data"]["id"]
        self.assertFalse(WarehouseStock.objects.filter(variant=self.variant).exists())
        response = self.client.post(f"/api/inventory/supplies/{supply_id}/receive")
        self.assertEqual(response.status_code, 200)
        stock = WarehouseStock.objects.get(variant=self.variant, warehouse=self.warehouse)
        self.assertEqual((stock.quantity, stock.sellable, stock.reserved), (7, 7, 0))

    def test_second_receive_is_rejected_without_side_effects(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        self.assertEqual(self.client.post(f"/api/inventory/supplies/{supply_id}/receive").status_code, 200)
        first_received_at = InventorySupply.objects.get(id=supply_id).received_at
        rejected = self.client.post(f"/api/inventory/supplies/{supply_id}/receive")
        self.assertEqual(rejected.status_code, 400)
        supply = InventorySupply.objects.get(id=supply_id)
        self.assertEqual(supply.received_at, first_received_at)
        stock = WarehouseStock.objects.get(variant=self.variant)
        self.assertEqual((stock.quantity, stock.sellable), (10, 10))

    def test_received_supply_restrictions_and_allowed_edits(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        self.assertEqual(self.client.post(f"/api/inventory/supplies/{supply_id}/receive").status_code, 200)

        for payload in (
            {"variant_id": self.serialized_variant.id},
            {"warehouse_id": self.second_warehouse.id},
            {"quantity": 99},
        ):
            rejected = self.client.patch(f"/api/inventory/supplies/{supply_id}", payload, format="json")
            self.assertEqual(rejected.status_code, 400, payload)

        allowed = self.client.patch(
            f"/api/inventory/supplies/{supply_id}",
            {
                "unit_buy_price": "150.00",
                "reference_number": "PO-EDITED",
                "notes": "Edited after receiving",
                "costs": [{"type": "shipment", "amount": "10.00"}],
            },
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        detail = allowed.data["data"]
        self.assertEqual(detail["unit_buy_price"], "150.00")
        self.assertEqual(detail["extra_cost_total"], "10.00")
        self.assertTrue(detail["is_received"])

    def test_received_supply_cannot_be_deleted(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        self.client.post(f"/api/inventory/supplies/{supply_id}/receive")
        deleted = self.client.delete(f"/api/inventory/supplies/{supply_id}")
        self.assertEqual(deleted.status_code, 400)
        self.assertIn("Received supplies cannot be deleted", str(deleted.data))
        self.assertTrue(InventorySupply.objects.filter(id=supply_id).exists())

    def test_receive_serialized_requires_matching_serial_count(self):
        created = self.create_serialized_supply(quantity=2)
        supply_id = created.data["data"]["id"]
        too_few = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [{"serial_number": "SERIAL-1"}]},
            format="json",
        )
        self.assertEqual(too_few.status_code, 400)
        too_many = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [
                {"serial_number": "SERIAL-1"},
                {"serial_number": "SERIAL-2"},
                {"serial_number": "SERIAL-3"},
            ]},
            format="json",
        )
        self.assertEqual(too_many.status_code, 400)
        missing = self.client.post(f"/api/inventory/supplies/{supply_id}/receive")
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(SerializedStock.objects.count(), 0)
        self.assertIsNone(InventorySupply.objects.get(id=supply_id).received_at)

        ok = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [{"serial_number": " SERIAL   1 "}, {"serial_number": "SERIAL-2"}]},
            format="json",
        )
        self.assertEqual(ok.status_code, 200)
        rows = list(SerializedStock.objects.order_by("id"))
        self.assertEqual([row.serial_number for row in rows], ["SERIAL 1", "SERIAL-2"])
        for row in rows:
            self.assertEqual(row.supply_id, supply_id)
            self.assertEqual(row.variant_id, self.serialized_variant.id)
            self.assertEqual(row.warehouse_id, self.warehouse.id)
            self.assertEqual(row.status.code, "in_stock")
            self.assertTrue(row.sellable)
            self.assertFalse(row.reserved)
        supply = InventorySupply.objects.get(id=supply_id)
        self.assertIsNotNone(supply.received_at)
        self.assertEqual(supply.remaining_quantity, 2)

    def test_receive_serialized_rejects_duplicate_serials_with_full_rollback(self):
        SerializedStock.objects.create(
            variant=self.serialized_variant,
            warehouse=self.warehouse,
            status=self.in_stock_status,
            serial_number="EXISTING",
        )
        created = self.create_serialized_supply(quantity=3)
        supply_id = created.data["data"]["id"]

        batch_dupes = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [
                {"serial_number": "NEW-1"},
                {"serial_number": "new-1"},
                {"serial_number": "NEW-3"},
            ]},
            format="json",
        )
        self.assertEqual(batch_dupes.status_code, 400)

        global_dupe = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [
                {"serial_number": "NEW-A"},
                {"serial_number": "existing"},
                {"serial_number": "NEW-C"},
            ]},
            format="json",
        )
        self.assertEqual(global_dupe.status_code, 400)

        self.assertEqual(SerializedStock.objects.count(), 1)
        self.assertTrue(SerializedStock.objects.filter(serial_number="EXISTING").exists())
        supply = InventorySupply.objects.get(id=supply_id)
        self.assertIsNone(supply.received_at)
        self.assertFalse(supply.is_received)

    def test_normal_receive_rejects_serial_items(self):
        created = self.create_supply()
        supply_id = created.data["data"]["id"]
        rejected = self.client.post(
            f"/api/inventory/supplies/{supply_id}/receive",
            {"serial_items": [{"serial_number": "SN-1"}]},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(WarehouseStock.objects.count(), 0)

    def test_received_filter_and_list_expose_receiving_state(self):
        untouched = self.create_supply()
        received = self.create_serialized_supply(quantity=1)
        received_id = received.data["data"]["id"]
        self.client.post(
            f"/api/inventory/supplies/{received_id}/receive",
            {"serial_items": [{"serial_number": "FILTER-SN"}]},
            format="json",
        )
        received_only = self.client.get("/api/inventory/supplies", {"received": "true"})
        self.assertEqual(received_only.data["data"]["count"], 1)
        self.assertTrue(received_only.data["data"]["results"][0]["is_received"])
        pending_only = self.client.get("/api/inventory/supplies", {"received": "false"})
        self.assertEqual(pending_only.data["data"]["count"], 1)
        self.assertEqual(pending_only.data["data"]["results"][0]["id"], untouched.data["data"]["id"])


class SupplyConsumptionTests(TestCase):
    def setUp(self):
        self.supply_service = InventorySupplyService()
        country = Country.objects.create(name="Consume Country", code="CX", phone_code="+1")
        state = State.objects.create(name="Consume State", country=country)
        city = City.objects.create(name="Consume City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-consume-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-CONSUME",
            name="Consume Warehouse",
            city=city,
            address="Consume address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        self.serialized, _ = InventoryStrategy.objects.update_or_create(
            code="serialized", defaults={"name": "Serialized"}
        )
        self.in_stock_status, _ = SerializedStockStatus.objects.update_or_create(
            code="in_stock", defaults={"name": "in_stock"}
        )
        category_status = CategoryStatus.objects.create(name="consume-active")
        product_status = ProductStatus.objects.create(name="consume-pending")
        category = Category.objects.create(name="Consume Category", status=category_status)
        product = Product.objects.create(name="Consume Product", status=product_status)
        product.categories.add(category)
        self.variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="CONSUME-SKU",
            combination_key="consume-sku",
            price="10.00",
        )
        self.serialized_variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.serialized,
            sku="CONSUME-SER",
            combination_key="consume-ser",
            price="10.00",
        )

    def received_supply(self, *, variant=None, quantity=5, unit_buy_price="100.00",
                        costs=None, serial_numbers=None):
        supply = self.supply_service.create_supply(
            variant=variant or self.variant,
            warehouse=self.warehouse,
            quantity=quantity,
            unit_buy_price=Decimal(unit_buy_price),
            supplied_at=timezone.make_aware(datetime(2026, 1, 10)),
            costs=[
                {"type": "shipment", "amount": amount}
                for amount in (costs or [])
            ],
        )
        if serial_numbers is None:
            return self.supply_service.receive_supply(supply)
        return self.supply_service.receive_supply(
            supply,
            serial_items=[{"serial_number": value} for value in serial_numbers],
        )

    def make_order_item(self, *, variant=None, quantity=1, reservation_type=None, reservation_ids=None):
        customer_status, _ = CustomerStatus.objects.get_or_create(
            name="active-consume", defaults={"title": "Active"}
        )
        self._customer_seq = getattr(self, "_customer_seq", 0) + 1
        customer = Customer.objects.create_user(
            phone=f"+98912000001{self._customer_seq}",
            first_name="Consume",
            last_name="Tester",
            customer_code=f"CUS-CONSUME-{self._customer_seq}",
            status=customer_status,
        )
        order_status, _ = OrderStatus.objects.get_or_create(
            name="payment_pending-consume", defaults={"fa_name": "pending"}
        )
        order = Order.objects.create(
            customer=customer,
            status=order_status,
            address_info={},
            subtotal=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("10.00"),
        )
        variant = variant or self.variant
        item = OrderItem.objects.create(
            order=order,
            variant=variant,
            sku=variant.sku,
            quantity=quantity,
            unit_price=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            final_price=Decimal("10.00"),
            inventory_strategy=variant.inventory_strategy,
        )
        if reservation_ids:
            inventory_type = reservation_type or (
                "serialized_stock" if variant.inventory_strategy.code == "serialized" else "warehouse_stock"
            )
            for inventory_id in reservation_ids:
                OrderItemReservation.objects.create(
                    order_item=item,
                    inventory_type=inventory_type,
                    inventory_id=inventory_id,
                    quantity=quantity if len(reservation_ids) == 1 else 1,
                )
        return item

    def remaining_of(self, supply_id):
        return InventorySupply.objects.get(id=supply_id).remaining_quantity

    def test_fifo_consumes_oldest_supplies_first_across_layers(self):
        old = self.received_supply(quantity=3, unit_buy_price="100.00")
        newer = self.received_supply(
            quantity=5, unit_buy_price="200.00", costs=["100.00"],
        )
        # Make the second supply clearly younger.
        InventorySupply.objects.filter(id=newer.id).update(
            supplied_at=timezone.make_aware(datetime(2026, 2, 10))
        )
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(
            quantity=6, reservation_ids=[stock.id],
        )

        consumptions = self.supply_service.consume_order_item(item)

        self.assertEqual(len(consumptions), 2)
        self.assertEqual(self.remaining_of(old.id), 0)
        self.assertEqual(self.remaining_of(newer.id), 2)
        by_supply = {row.supply_id: row for row in consumptions}
        self.assertEqual(by_supply[old.id].quantity, 3)
        self.assertEqual(by_supply[newer.id].quantity, 3)
        self.assertEqual(by_supply[old.id].unit_cost, Decimal("100.00"))
        self.assertEqual(by_supply[old.id].total_cost, Decimal("300.00"))
        self.assertEqual(by_supply[newer.id].unit_cost, Decimal("220.00"))
        self.assertEqual(by_supply[newer.id].total_cost, Decimal("660.00"))

    def test_consumption_runs_through_order_finalize_hook(self):
        supply = self.received_supply(quantity=4, unit_buy_price="50.00")
        item = self.make_order_item(quantity=2)
        stock = WarehouseStock.objects.get(variant=self.variant)
        # Checkout reserves by incrementing reserved before finalization.
        WarehouseStock.objects.filter(id=stock.id).update(reserved=2)
        OrderItemReservation.objects.create(
            order_item=item,
            inventory_type="warehouse_stock",
            inventory_id=stock.id,
            quantity=2,
        )
        OrderService().consume_reservations(item.order)
        self.assertEqual(self.remaining_of(supply.id), 2)
        self.assertTrue(
            InventorySupplyConsumption.objects.filter(order_item=item, supply=supply).exists()
        )
        stock.refresh_from_db()
        self.assertEqual((stock.quantity, stock.sellable, stock.reserved), (4, 2, 0))

    def test_unit_cost_snapshot_is_immutable_after_price_changes(self):
        supply = self.received_supply(quantity=4, unit_buy_price="100.00", costs=["100.00"])
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=2, reservation_ids=[stock.id])
        self.supply_service.consume_order_item(item)
        consumption = InventorySupplyConsumption.objects.get(order_item=item)
        self.assertEqual(consumption.unit_cost, Decimal("125.00"))
        self.assertEqual(consumption.total_cost, Decimal("250.00"))

        InventorySupply.objects.filter(id=supply.id).update(unit_buy_price=Decimal("999.00"))
        consumption.refresh_from_db()
        self.assertEqual(consumption.unit_cost, Decimal("125.00"))
        self.assertEqual(consumption.total_cost, Decimal("250.00"))

    def test_insufficient_remaining_quantity_fails_atomically(self):
        supply = self.received_supply(quantity=4, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=6, reservation_ids=[stock.id])
        with self.assertRaises(self.supply_service.ValidationError), transaction.atomic():
            self.supply_service.consume_order_item(item)
        self.assertEqual(self.remaining_of(supply.id), 4)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

        # Partially available layers must not be partially consumed either.
        other_item = self.make_order_item(
            quantity=5, reservation_ids=[stock.id],
        )
        with self.assertRaises(self.supply_service.ValidationError), transaction.atomic():
            self.supply_service.consume_order_item(other_item)
        self.assertEqual(self.remaining_of(supply.id), 4)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

    def test_duplicate_consumption_is_prevented(self):
        self.received_supply(quantity=5, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=2, reservation_ids=[stock.id])
        self.supply_service.consume_order_item(item)
        first_count = InventorySupplyConsumption.objects.count()
        with self.assertRaises(self.supply_service.ValidationError), transaction.atomic():
            self.supply_service.consume_order_item(item)
        self.assertEqual(InventorySupplyConsumption.objects.count(), first_count)

    def test_reservations_alone_do_not_consume_supply(self):
        supply = self.received_supply(quantity=5, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant, warehouse=self.warehouse)
        WarehouseStock.objects.filter(id=stock.id).update(reserved=2)
        item = self.make_order_item(quantity=2)
        OrderItemReservation.objects.create(
            order_item=item,
            inventory_type="warehouse_stock",
            inventory_id=stock.id,
            quantity=2,
        )
        self.assertEqual(self.remaining_of(supply.id), 5)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

    def test_serialized_consumption_uses_exact_linked_supplies(self):
        first = self.received_supply(
            variant=self.serialized_variant, quantity=2,
            unit_buy_price="100.00", serial_numbers=["SN-A", "SN-B"],
        )
        second = self.received_supply(
            variant=self.serialized_variant, quantity=3,
            unit_buy_price="200.00", serial_numbers=["SN-C", "SN-D", "SN-E"],
        )
        sold_rows = SerializedStock.objects.filter(serial_number__in=["SN-B", "SN-D"])
        self.assertEqual(sold_rows.count(), 2)
        item = self.make_order_item(
            variant=self.serialized_variant,
            quantity=2,
            reservation_type="serialized_stock",
            reservation_ids=list(sold_rows.values_list("id", flat=True)),
        )

        self.supply_service.consume_order_item(item)

        self.assertEqual(self.remaining_of(first.id), 1)
        self.assertEqual(self.remaining_of(second.id), 2)
        rows = InventorySupplyConsumption.objects.filter(order_item=item)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            {(row.supply_id, row.quantity) for row in rows},
            {(first.id, 1), (second.id, 1)},
        )

    def test_serialized_units_without_supply_linkage_are_skipped(self):
        SerializedStock.objects.create(
            variant=self.serialized_variant,
            warehouse=self.warehouse,
            status=self.in_stock_status,
            serial_number="LEGACY-SN",
        )
        legacy_row = SerializedStock.objects.get(serial_number="LEGACY-SN")
        item = self.make_order_item(
            variant=self.serialized_variant,
            quantity=1,
            reservation_type="serialized_stock",
            reservation_ids=[legacy_row.id],
        )
        self.supply_service.consume_order_item(item)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

    def test_untracked_normal_stock_sells_without_consumption(self):
        WarehouseStock.objects.create(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=10,
            sellable=10,
        )
        item = self.make_order_item(quantity=3)
        consumptions = self.supply_service.consume_order_item(item)
        self.assertEqual(consumptions, [])
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

    def test_multi_item_failure_rolls_back_entire_transaction(self):
        good = self.received_supply(quantity=2, unit_buy_price="100.00")
        short = self.received_supply(
            quantity=2, unit_buy_price="100.00",
        )
        InventorySupply.objects.filter(id=short.id).update(
            supplied_at=timezone.make_aware(datetime(2026, 3, 10))
        )
        stock = WarehouseStock.objects.get(variant=self.variant)
        first_item = self.make_order_item(quantity=2, reservation_ids=[stock.id])
        second_item = self.make_order_item(quantity=5, reservation_ids=[stock.id])

        # Mimics payment review: the caller wraps finalization in one atomic
        # block, so a failed item must undo already-consumed items too.
        with self.assertRaises(self.supply_service.ValidationError):
            with transaction.atomic():
                self.supply_service.consume_order_item(first_item)
                self.supply_service.consume_order_item(second_item)

        self.assertEqual(self.remaining_of(good.id), 2)
        self.assertEqual(self.remaining_of(short.id), 2)
        self.assertEqual(InventorySupplyConsumption.objects.count(), 0)

    # ─────────────────────── Step 6: reversal ───────────────────────

    def consumed_across_two_supplies(self):
        old = self.received_supply(quantity=3, unit_buy_price="100.00")
        newer = self.received_supply(quantity=5, unit_buy_price="200.00", costs=["100.00"])
        InventorySupply.objects.filter(id=newer.id).update(
            supplied_at=timezone.make_aware(datetime(2026, 2, 10))
        )
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=6, reservation_ids=[stock.id])
        consumptions = self.supply_service.consume_order_item(item)
        return old, newer, item, consumptions

    def test_full_reversal_restores_exact_original_supplies(self):
        old, newer, item, _ = self.consumed_across_two_supplies()
        self.assertEqual(self.remaining_of(old.id), 0)
        self.assertEqual(self.remaining_of(newer.id), 2)

        reversed_total = self.supply_service.reverse_order_item_consumption(item)

        self.assertEqual(reversed_total, 6)
        self.assertEqual(self.remaining_of(old.id), 3)
        self.assertEqual(self.remaining_of(newer.id), 5)
        for record in InventorySupplyConsumption.objects.filter(order_item=item):
            self.assertEqual(record.reversed_quantity, record.quantity)

    def test_partial_reversal_prefers_most_recent_layer_first(self):
        old, newer, item, _ = self.consumed_across_two_supplies()

        reversed_total = self.supply_service.reverse_order_item_consumption(item, quantity=4)

        self.assertEqual(reversed_total, 4)
        # Most recent layer (newer) absorbs 3, then older layer takes 1.
        self.assertEqual(self.remaining_of(newer.id), 5)
        self.assertEqual(self.remaining_of(old.id), 1)
        by_supply = {r.supply_id: r for r in InventorySupplyConsumption.objects.filter(order_item=item)}
        self.assertEqual(by_supply[newer.id].reversed_quantity, 3)
        self.assertEqual(by_supply[old.id].reversed_quantity, 1)

    def test_reversal_never_exceeds_consumed_quantity(self):
        _, _, item, _ = self.consumed_across_two_supplies()
        with self.assertRaises(self.supply_service.ValidationError), transaction.atomic():
            self.supply_service.reverse_order_item_consumption(item, quantity=7)
        with self.assertRaises(self.supply_service.ValidationError), transaction.atomic():
            self.supply_service.reverse_order_item_consumption(item, quantity=0)

        consumption = InventorySupplyConsumption.objects.filter(order_item=item).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventorySupplyConsumption.objects.filter(id=consumption.id).update(
                reversed_quantity=consumption.quantity + 1
            )
        consumption.refresh_from_db()
        self.assertEqual(consumption.reversed_quantity, 0)

    def test_repeated_full_reversal_does_not_restore_twice(self):
        supply = self.received_supply(quantity=4, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=2, reservation_ids=[stock.id])
        self.supply_service.consume_order_item(item)
        self.assertEqual(self.remaining_of(supply.id), 2)

        first = self.supply_service.reverse_order_item_consumption(item)
        second = self.supply_service.reverse_order_item_consumption(item)

        self.assertEqual((first, second), (2, 0))
        self.assertEqual(self.remaining_of(supply.id), 4)
        self.assertTrue(all(
            r.reversed_quantity == r.quantity
            for r in InventorySupplyConsumption.objects.filter(order_item=item)
        ))

    def test_serialized_reversal_restores_linked_supplies(self):
        first = self.received_supply(
            variant=self.serialized_variant, quantity=2,
            unit_buy_price="100.00", serial_numbers=["RSN-A", "RSN-B"],
        )
        second = self.received_supply(
            variant=self.serialized_variant, quantity=2,
            unit_buy_price="200.00", serial_numbers=["RSN-C", "RSN-D"],
        )
        sold_rows = SerializedStock.objects.filter(serial_number__in=["RSN-A", "RSN-C"])
        item = self.make_order_item(
            variant=self.serialized_variant,
            quantity=2,
            reservation_type="serialized_stock",
            reservation_ids=list(sold_rows.values_list("id", flat=True)),
        )
        self.supply_service.consume_order_item(item)
        self.assertEqual(self.remaining_of(first.id), 1)
        self.assertEqual(self.remaining_of(second.id), 1)

        reversed_total = self.supply_service.reverse_order_item_consumption(item)

        self.assertEqual(reversed_total, 2)
        self.assertEqual(self.remaining_of(first.id), 2)
        self.assertEqual(self.remaining_of(second.id), 2)
        rows = InventorySupplyConsumption.objects.filter(order_item=item)
        self.assertTrue(all(r.reversed_quantity == r.quantity for r in rows))

    def test_failed_reversal_rolls_back_entire_transaction(self):
        supply = self.received_supply(quantity=4, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=4, reservation_ids=[stock.id])
        self.supply_service.consume_order_item(item)
        self.assertEqual(self.remaining_of(supply.id), 0)

        with self.assertRaises(self.supply_service.ValidationError):
            with transaction.atomic():
                reversed_total = self.supply_service.reverse_order_item_consumption(item)
                self.assertEqual(reversed_total, 4)
                # Any failure in the same caller transaction must undo the reversal.
                raise self.supply_service.ValidationError({"force": ["boom"]})

        self.assertEqual(self.remaining_of(supply.id), 0)
        self.assertTrue(all(
            r.reversed_quantity == 0
            for r in InventorySupplyConsumption.objects.filter(order_item=item)
        ))

    def test_cancel_action_reverses_consumed_layers(self):
        from core.management.seeders.order import OrderSeeder

        OrderSeeder().run()
        supply = self.received_supply(quantity=4, unit_buy_price="100.00")
        status = OrderStatus.objects.get(name="payment_pending")
        customer_status, _ = CustomerStatus.objects.get_or_create(
            name="active-consume", defaults={"title": "Active"}
        )
        customer = Customer.objects.create_user(
            phone="+989120000099",
            first_name="Cancel",
            last_name="Tester",
            customer_code="CUS-CONSUME-CANCEL",
            status=customer_status,
        )
        order = Order.objects.create(
            customer=customer,
            status=status,
            address_info={},
            subtotal=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("10.00"),
        )
        stock = WarehouseStock.objects.get(variant=self.variant)
        WarehouseStock.objects.filter(id=stock.id).update(reserved=2)
        consumed_item = OrderItem.objects.create(
            order=order,
            variant=self.variant,
            sku=self.variant.sku,
            quantity=2,
            unit_price=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            final_price=Decimal("20.00"),
            inventory_strategy=self.normal,
        )
        OrderItemReservation.objects.create(
            order_item=consumed_item,
            inventory_type="warehouse_stock",
            inventory_id=stock.id,
            quantity=2,
        )
        # Finalize the sale through the real consumption path first.
        self.supply_service.consume_order_item(consumed_item)
        self.assertEqual(self.remaining_of(supply.id), 2)
        untouched_item = OrderItem.objects.create(
            order=order,
            variant=self.serialized_variant,
            sku=self.serialized_variant.sku,
            quantity=1,
            unit_price=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            final_price=Decimal("10.00"),
            inventory_strategy=self.serialized,
        )
        admin = User.objects.create_superuser("reversal-admin", password="password")

        response = OrderService().execute_action(
            order.id, "cancel", actor="admin", admin=admin
        )
        self.assertIsNotNone(response)
        self.assertEqual(self.remaining_of(supply.id), 4)
        record = InventorySupplyConsumption.objects.get(order_item=consumed_item)
        self.assertEqual(record.reversed_quantity, 2)
        # The unconsumed item reverses nothing and raises no error.
        self.assertFalse(untouched_item.supply_consumptions.exists())

    def test_return_completion_reverses_returned_quantities_only(self):
        supply = self.received_supply(quantity=4, unit_buy_price="100.00")
        stock = WarehouseStock.objects.get(variant=self.variant)
        item = self.make_order_item(quantity=2, reservation_ids=[stock.id])
        self.supply_service.consume_order_item(item)
        self.assertEqual(self.remaining_of(supply.id), 2)

        customer = item.order.customer
        request = ReturnRequest.objects.create(
            order=item.order,
            customer=customer,
            reason="Damaged unit",
            refund_destination_type=ReturnRequest.RefundDestinationType.CARD,
            refund_destination_value="6104-1234-5678-9012",
        )
        ReturnRequestItem.objects.create(
            return_request=request,
            order_item=item,
            quantity=1,
        )
        service = ReturnRequestService()
        service.execute_admin_action(item.order_id, request.id, "approve")
        service.execute_admin_action(item.order_id, request.id, "received")
        service.execute_admin_action(item.order_id, request.id, "complete")

        self.assertEqual(self.remaining_of(supply.id), 3)
        record = InventorySupplyConsumption.objects.get(order_item=item)
        self.assertEqual(record.reversed_quantity, 1)


class VariantPricingAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="pricing-admin", password="password")
        self.client.force_authenticate(self.user)
        country = Country.objects.create(name="Pricing Country", code="PC", phone_code="+1")
        state = State.objects.create(name="Pricing State", country=country)
        city = City.objects.create(name="Pricing City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-pricing-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-PRICING",
            name="Pricing Warehouse",
            city=city,
            address="Pricing address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        category_status = CategoryStatus.objects.create(name="pricing-active")
        product_status = ProductStatus.objects.create(name="pricing-pending")
        category = Category.objects.create(name="Pricing Category", status=category_status)
        product = Product.objects.create(name="Pricing Product", status=product_status)
        product.categories.add(category)
        self.category = category
        self.variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="PRICING-SKU",
            combination_key="pricing-sku",
            price="10.00",
        )
        self.other_variant = ProductVariants.objects.create(
            product=product,
            inventory_strategy=self.normal,
            sku="PRICING-SKU-2",
            combination_key="pricing-sku-2",
            price="10.00",
        )

    def received_supply(self, *, variant=None, quantity=5, unit_buy_price="100.00",
                        costs=None, remaining=None, day=1):
        from domains.inventory.services import InventorySupplyService

        supply = InventorySupplyService().create_supply(
            variant=variant or self.variant,
            warehouse=self.warehouse,
            quantity=quantity,
            unit_buy_price=Decimal(unit_buy_price),
            supplied_at=timezone.make_aware(datetime(2026, 1, day)),
            costs=[{"type": "shipment", "amount": amount} for amount in (costs or [])],
        )
        if remaining is None:
            InventorySupplyService().receive_supply(supply)
        else:
            # Received without full stock-side setup; costing only needs
            # received_at plus a known remaining quantity.
            InventorySupply.objects.filter(id=supply.id).update(
                received_at=timezone.make_aware(datetime(2026, 1, day)),
                remaining_quantity=remaining,
            )
        return InventorySupply.objects.get(id=supply.id)

    def pricing_url(self, variant=None):
        return f"/api/inventory/variants/{(variant or self.variant).id}/pricing"

    def test_get_returns_overview_with_nulls_when_unconfigured(self):
        response = self.client.get(self.pricing_url())
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertIsNotNone(data)
        self.assertEqual(data["variant_id"], self.variant.id)
        self.assertIsNone(data["cost_strategy"])
        self.assertIsNone(data["expected_profit_percentage"])
        self.assertIsNone(data["cost_basis"])
        self.assertIsNone(data["suggested_price"])
        self.assertIsNone(data["latest_cost"])
        self.assertEqual(data["total_remaining_supply_quantity"], 0)

    def test_patch_creates_and_get_returns_config(self):
        created = self.client.patch(
            self.pricing_url(),
            {"expected_profit_percentage": "25.50", "cost_strategy": "weighted_average"},
            format="json",
        )
        self.assertEqual(created.status_code, 200)
        data = created.data["data"]
        self.assertEqual(data["variant_id"], self.variant.id)
        self.assertEqual(data["expected_profit_percentage"], "25.50")
        self.assertEqual(data["cost_strategy"], "weighted_average")

        fetched = self.client.get(self.pricing_url())
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data["data"]["cost_strategy"], "weighted_average")

    def test_only_one_config_per_variant(self):
        first = self.client.patch(
            self.pricing_url(), {"cost_strategy": "latest"}, format="json"
        )
        second = self.client.patch(
            self.pricing_url(),
            {"expected_profit_percentage": "10.00", "cost_strategy": "fifo_next"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(VariantPricing.objects.filter(variant=self.variant).count(), 1)
        config = VariantPricing.objects.get(variant=self.variant)
        self.assertEqual((config.cost_strategy, str(config.expected_profit_percentage)), ("fifo_next", "10.00"))

        with self.assertRaises(IntegrityError), transaction.atomic():
            VariantPricing.objects.create(
                variant=self.variant,
                expected_profit_percentage=Decimal("1.00"),
                cost_strategy="latest",
            )

    def test_negative_expected_profit_is_rejected(self):
        rejected = self.client.patch(
            self.pricing_url(), {"expected_profit_percentage": "-0.01"}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VariantPricing.objects.create(
                variant=self.other_variant,
                expected_profit_percentage=Decimal("-5.00"),
                cost_strategy="latest",
            )
        self.assertFalse(VariantPricing.objects.filter(variant=self.variant).exists())

    def test_all_valid_strategies_are_accepted(self):
        for strategy in ("latest", "weighted_average", "fifo_next"):
            response = self.client.patch(
                self.pricing_url(variant=self.other_variant),
                {"cost_strategy": strategy},
                format="json",
            )
            self.assertEqual(response.status_code, 200, strategy)
            self.assertEqual(response.data["data"]["cost_strategy"], strategy)

    def test_invalid_strategy_is_rejected(self):
        rejected = self.client.patch(
            self.pricing_url(), {"cost_strategy": "delivery_magic"}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("cost_strategy", rejected.data["errors"])
        self.assertFalse(VariantPricing.objects.exists())

    def test_unknown_fields_and_empty_payloads_are_rejected(self):
        unknown = self.client.patch(
            self.pricing_url(),
            {"expected_profit_percentage": "10.00", "suggested_price": "99.00"},
            format="json",
        )
        self.assertEqual(unknown.status_code, 400)
        empty = self.client.patch(self.pricing_url(), {}, format="json")
        self.assertEqual(empty.status_code, 400)
        self.assertFalse(VariantPricing.objects.exists())

    def test_pricing_for_missing_variant_returns_404(self):
        missing = self.client.get("/api/inventory/variants/999999/pricing")
        self.assertEqual(missing.status_code, 404)

    def test_pricing_strategies_endpoint_lists_enum_options(self):
        response = self.client.get("/api/inventory/pricing-strategies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(item["code"], item["name"]) for item in response.data["data"]],
            [
                ("latest", "Latest"),
                ("weighted_average", "Weighted average"),
                ("fifo_next", "FIFO next"),
            ],
        )

    def test_permissions_are_enforced(self):
        staff = User.objects.create_user(username="pricing-staff", is_staff=True)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.pricing_url()).status_code, (401, 403))

        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.pricing_url()).status_code, 403)
        self.assertEqual(
            self.client.patch(self.pricing_url(), {"cost_strategy": "latest"}, format="json").status_code,
            403,
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_inventory"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.pricing_url()).status_code, 200)
        self.assertEqual(
            self.client.patch(self.pricing_url(), {"cost_strategy": "latest"}, format="json").status_code,
            403,
        )
        staff.user_permissions.add(Permission.objects.get(codename="adjust_stock"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.patch(self.pricing_url(), {"cost_strategy": "latest"}, format="json").status_code,
            200,
        )

    def configure(self, variant=None, *, strategy, profit="20.00"):
        response = self.client.patch(
            self.pricing_url(variant),
            {"cost_strategy": strategy, "expected_profit_percentage": profit},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return response.data["data"]

    def test_latest_strategy_uses_newest_received_supply_landed_cost(self):
        old = self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        newer = self.received_supply(
            quantity=4, unit_buy_price="200.00", costs=["40.00"], day=2
        )
        data = self.configure(strategy="latest")
        # Newer landed unit cost: (4 * 200 + 40) / 4 = 210.
        self.assertEqual(data["cost_basis"], "210.00")
        self.assertEqual(data["suggested_price"], "252.00")
        self.assertEqual(data["total_remaining_supply_quantity"], old.remaining_quantity + newer.remaining_quantity)
        self.assertEqual(data["catalog_price"], "10.00")

    def test_fifo_next_strategy_uses_oldest_remaining_supply(self):
        self.received_supply(quantity=5, unit_buy_price="200.00", day=1)
        newest = self.received_supply(quantity=3, unit_buy_price="90.00", day=2)
        data = self.configure(strategy="fifo_next", profit="25.00")
        self.assertEqual(data["cost_basis"], "200.00")
        self.assertEqual(data["suggested_price"], "250.00")
        self.assertNotEqual(data["cost_basis"], str(newest.unit_buy_price))

    def test_weighted_average_strategy_weights_remaining_quantities(self):
        self.received_supply(quantity=10, unit_buy_price="100.00", remaining=6, day=1)
        self.received_supply(
            quantity=4, unit_buy_price="200.00", costs=["40.00"], remaining=4, day=2
        )
        data = self.configure(strategy="weighted_average")
        # (6*100 + 4*210) / 10 = 144.
        self.assertEqual(data["cost_basis"], "144.00")
        self.assertEqual(data["suggested_price"], "172.80")
        self.assertEqual(data["total_remaining_supply_quantity"], 10)

    def test_only_received_supplies_are_used(self):
        unreceived = InventorySupplyService().create_supply(
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=50,
            unit_buy_price=Decimal("1000.00"),
            supplied_at=timezone.make_aware(datetime(2026, 5, 1)),
        )
        received = self.received_supply(quantity=2, unit_buy_price="50.00", day=1)
        data = self.configure(strategy="latest")
        self.assertEqual(data["cost_basis"], "50.00")
        self.assertEqual(data["total_remaining_supply_quantity"], received.remaining_quantity)
        self.assertIsNotNone(unreceived.id)

    def test_zero_remaining_supplies_are_ignored(self):
        consumed = self.received_supply(quantity=5, unit_buy_price="999.00", day=1)
        InventorySupply.objects.filter(id=consumed.id).update(remaining_quantity=0)
        active = self.received_supply(quantity=3, unit_buy_price="80.00", day=2)
        data = self.configure(strategy="fifo_next")
        self.assertEqual(data["cost_basis"], "80.00")
        self.assertEqual(data["total_remaining_supply_quantity"], active.remaining_quantity)

    def test_weighted_average_decimal_math_is_exact(self):
        self.received_supply(quantity=3, unit_buy_price="30.00", remaining=1, day=1)
        self.received_supply(
            quantity=3, unit_buy_price="33.33", costs=["0.01"], remaining=2, day=2
        )
        data = self.configure(strategy="weighted_average")
        # Layer 2 landed unit cost is 100/3 (non-terminating); the weighted
        # average is exactly 290/9 and must round once at the boundary.
        self.assertEqual(data["cost_basis"], "32.22")
        self.assertEqual(data["suggested_price"], "38.67")

    def test_missing_supplies_yield_null_cost_and_suggested_price(self):
        data = self.configure(strategy="latest")
        self.assertIsNone(data["cost_basis"])
        self.assertIsNone(data["suggested_price"])
        self.assertEqual(data["total_remaining_supply_quantity"], 0)
        self.assertEqual(data["cost_strategy"], "latest")

        fully_consumed = self.received_supply(quantity=3, unit_buy_price="10.00", day=1)
        InventorySupply.objects.filter(id=fully_consumed.id).update(remaining_quantity=0)
        still_null = self.client.get(self.pricing_url())
        self.assertIsNone(still_null.data["data"]["cost_basis"])

    def test_calculation_never_modifies_catalog_price(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        original_price = ProductVariants.objects.get(id=self.variant.id).price
        self.configure(strategy="latest", profit="50.00")
        fetched = self.client.get(self.pricing_url())
        self.assertEqual(fetched.data["data"]["suggested_price"], "150.00")
        self.assertEqual(fetched.data["data"]["catalog_price"], "10.00")
        self.assertEqual(
            ProductVariants.objects.get(id=self.variant.id).price,
            original_price,
        )

    # ─────────────────── Step 9: admin pricing overview ───────────────────

    def test_pricing_list_is_paginated_and_shows_configured_and_unconfigured(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.configure(strategy="weighted_average", profit="20.00")
        response = self.client.get("/api/inventory/pricing")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, data)
        self.assertEqual(data["count"], 2)
        rows = {row["variant_id"]: row for row in data["results"]}
        configured = rows[self.variant.id]
        self.assertEqual(configured["sku"], "PRICING-SKU")
        self.assertEqual(configured["product_name"], "Pricing Product")
        self.assertEqual(configured["current_price"], "10.00")
        self.assertEqual(configured["cost_strategy"], "weighted_average")
        self.assertEqual(configured["expected_profit_percentage"], "20.00")
        self.assertEqual(configured["cost_basis"], "100.00")
        self.assertEqual(configured["suggested_price"], "120.00")
        self.assertEqual(configured["remaining_quantity"], 5)
        unconfigured = rows[self.other_variant.id]
        self.assertIsNone(unconfigured["cost_strategy"])
        self.assertIsNone(unconfigured["expected_profit_percentage"])
        self.assertIsNone(unconfigured["cost_basis"])
        self.assertIsNone(unconfigured["suggested_price"])
        self.assertEqual(unconfigured["remaining_quantity"], 0)

    def test_pricing_list_search_by_sku_and_product_name(self):
        other_product = Product.objects.create(
            name="Gadget Searchable", status=ProductStatus.objects.first()
        )
        other_product.categories.add(self.category)
        other_variant = ProductVariants.objects.create(
            product=other_product,
            inventory_strategy=self.normal,
            sku="SEARCHABLE-SKU",
            combination_key="searchable-sku",
            price="5.00",
        )
        by_sku = self.client.get("/api/inventory/pricing", {"search": "SEARCHABLE-SKU"})
        self.assertEqual(by_sku.data["data"]["count"], 1)
        self.assertEqual(by_sku.data["data"]["results"][0]["variant_id"], other_variant.id)
        by_product = self.client.get("/api/inventory/pricing", {"search": "gadget searchable"})
        self.assertEqual(by_product.data["data"]["count"], 1)

    def test_pricing_list_strategy_filter(self):
        self.configure(variant=self.variant, strategy="latest")
        self.configure(variant=self.other_variant, strategy="fifo_next")
        latest_only = self.client.get("/api/inventory/pricing", {"strategy": "latest"})
        results = latest_only.data["data"]["results"]
        self.assertEqual(latest_only.data["data"]["count"], 1)
        self.assertEqual(results[0]["variant_id"], self.variant.id)
        invalid = self.client.get("/api/inventory/pricing", {"strategy": "delivery_magic"})
        self.assertEqual(invalid.status_code, 400)

    def test_pricing_list_has_pricing_filter(self):
        self.configure(variant=self.variant, strategy="latest")
        with_pricing = self.client.get("/api/inventory/pricing", {"has_pricing": "true"})
        self.assertEqual(with_pricing.data["data"]["count"], 1)
        without_pricing = self.client.get("/api/inventory/pricing", {"has_pricing": "false"})
        self.assertEqual(without_pricing.data["data"]["count"], 1)
        self.assertEqual(
            without_pricing.data["data"]["results"][0]["variant_id"],
            self.other_variant.id,
        )

    def test_pricing_list_category_filter(self):
        other_category = Category.objects.create(
            name="Other Pricing Category", status=CategoryStatus.objects.first()
        )
        other_product = Product.objects.create(
            name="Elsewhere Product", status=ProductStatus.objects.first()
        )
        other_product.categories.add(other_category)
        ProductVariants.objects.create(
            product=other_product,
            inventory_strategy=self.normal,
            sku="ELSEWHERE-SKU",
            combination_key="elsewhere-sku",
            price="1.00",
        )
        in_category = self.client.get(
            "/api/inventory/pricing", {"category_id": self.category.id}
        )
        self.assertEqual(in_category.data["data"]["count"], 2)

    def test_pricing_list_ordering_allowlist_with_fallback(self):
        cheap = ProductVariants.objects.create(
            product=self.variant.product,
            inventory_strategy=self.normal,
            sku="ORDER-CHEAP",
            combination_key="order-cheap",
            price="1.00",
        )
        expensive = ProductVariants.objects.create(
            product=self.variant.product,
            inventory_strategy=self.normal,
            sku="ORDER-EXPENSIVE",
            combination_key="order-expensive",
            price="900.00",
        )
        by_price = self.client.get("/api/inventory/pricing", {"ordering": "-current_price"})
        prices = [Decimal(row["current_price"]) for row in by_price.data["data"]["results"]]
        self.assertEqual(prices, sorted(prices, reverse=True))
        unsupported = self.client.get("/api/inventory/pricing", {"ordering": "hacker_field"})
        self.assertEqual(unsupported.status_code, 200)

    def test_pricing_detail_exposes_all_three_costs(self):
        old = self.received_supply(quantity=6, unit_buy_price="100.00", remaining=2, day=1)
        newer = self.received_supply(
            quantity=4, unit_buy_price="200.00", costs=["40.00"], remaining=3, day=2
        )
        self.configure(strategy="weighted_average", profit="10.00")
        detail = self.client.get(self.pricing_url())
        self.assertEqual(detail.status_code, 200)
        data = detail.data["data"]
        self.assertEqual(data["latest_cost"], "210.00")
        self.assertEqual(data["fifo_next_cost"], "100.00")
        # (2*100 + 3*210) / 5 = 166.
        self.assertEqual(data["weighted_average_cost"], "166.00")
        self.assertEqual(data["cost_basis"], "166.00")
        self.assertEqual(data["suggested_price"], "182.60")
        self.assertEqual(data["total_remaining_supply_quantity"], 5)
        self.assertEqual(data["catalog_price"], "10.00")
        self.assertEqual(ProductVariants.objects.get(id=self.variant.id).price, Decimal("10.00"))

    def test_pricing_list_query_count_is_bounded_per_page(self):
        for index in range(4):
            variant = ProductVariants.objects.create(
                product=self.variant.product,
                inventory_strategy=self.normal,
                sku=f"BULK-{index}",
                combination_key=f"bulk-{index}",
                price="10.00",
            )
            self.received_supply(
                variant=variant, quantity=3, unit_buy_price="50.00", day=index + 1
            )
            self.configure(
                variant=variant, strategy="fifo_next", profit="15.00"
            )
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as context:
            response = self.client.get("/api/inventory/pricing")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(context), 6)


    # ───────────────── Step 11: explicit price application ─────────────────

    def apply_url(self, variant=None):
        return f"{self.pricing_url(variant)}/apply"

    def history_url(self, variant=None):
        return f"{self.pricing_url(variant)}/history"

    def test_apply_suggested_price_changes_catalog_and_creates_history(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.configure(strategy="latest", profit="20.00")

        response = self.client.post(self.apply_url(), {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, Decimal("120.00"))
        history = VariantPriceHistory.objects.get(variant=self.variant)
        self.assertEqual(history.old_price, Decimal("10.00"))
        self.assertEqual(history.new_price, Decimal("120.00"))
        self.assertEqual(history.cost_basis, Decimal("100.00"))
        self.assertEqual(history.cost_strategy, "latest")
        self.assertEqual(history.expected_profit_percentage, Decimal("20.00"))
        self.assertEqual(history.source, "inventory_pricing")
        self.assertEqual(response.data["data"]["history"]["new_price"], "120.00")

    def test_custom_override_price_is_applied_and_snapshotted(self):
        self.received_supply(quantity=4, unit_buy_price="100.00", day=1)
        self.configure(strategy="fifo_next", profit="25.00")

        response = self.client.post(
            self.apply_url(), {"price": "130.00"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, Decimal("130.00"))
        history = VariantPriceHistory.objects.get(variant=self.variant)
        self.assertEqual(history.new_price, Decimal("130.00"))
        self.assertEqual(history.cost_basis, Decimal("100.00"))
        self.assertEqual(history.cost_strategy, "fifo_next")
        self.assertEqual(history.expected_profit_percentage, Decimal("25.00"))
        self.assertEqual(history.source, "manual")

    def test_price_history_endpoint_is_newest_first(self):
        self.received_supply(quantity=4, unit_buy_price="100.00", day=1)
        self.configure(strategy="latest", profit="20.00")
        first = self.client.post(self.apply_url(), {}, format="json")
        second = self.client.post(
            self.apply_url(), {"price": "140.00"}, format="json"
        )
        self.assertEqual((first.status_code, second.status_code), (200, 200))

        response = self.client.get(self.history_url())

        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["new_price"] for row in rows], ["140.00", "120.00"])
        self.assertEqual([row["source"] for row in rows], ["manual", "inventory_pricing"])

    def test_missing_cost_basis_prevents_apply(self):
        self.configure(strategy="latest", profit="20.00")
        original_price = Decimal(self.variant.price)

        response = self.client.post(self.apply_url(), {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, original_price)
        self.assertFalse(VariantPriceHistory.objects.exists())

    def test_apply_permission_requires_inventory_and_catalog_change(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.configure(strategy="latest", profit="20.00")
        staff = User.objects.create_user(username="price-applier", is_staff=True)
        view_permission = Permission.objects.get(codename="view_inventory")
        adjust_permission = Permission.objects.get(codename="adjust_stock")
        catalog_permission = Permission.objects.get(codename="change_productvariants")

        self.client.force_authenticate(staff)
        self.assertEqual(self.client.post(self.apply_url(), {}, format="json").status_code, 403)
        staff.user_permissions.add(view_permission, adjust_permission)
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.post(self.apply_url(), {}, format="json").status_code, 403)
        staff.user_permissions.add(catalog_permission)
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.post(self.apply_url(), {}, format="json").status_code, 200)

        history_reader = User.objects.create_user(username="price-reader", is_staff=True)
        history_reader.user_permissions.add(view_permission)
        self.client.force_authenticate(User.objects.get(pk=history_reader.pk))
        self.assertEqual(self.client.get(self.history_url()).status_code, 200)

    def test_failed_history_insert_rolls_back_price(self):
        from unittest.mock import patch

        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.configure(strategy="latest", profit="20.00")
        original_price = ProductVariants.objects.get(pk=self.variant.pk).price

        with patch(
            "domains.inventory.services.inventory_pricing_service."
            "VariantPriceHistory.objects.create",
            side_effect=IntegrityError("forced history failure"),
        ):
            with self.assertRaises(IntegrityError):
                InventoryPricingService().apply_price(self.variant)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, original_price)
        self.assertFalse(VariantPriceHistory.objects.exists())

    def test_configuration_changes_never_auto_apply_catalog_price(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        original_price = Decimal(self.variant.price)
        self.configure(strategy="latest", profit="50.00")
        InventorySupply.objects.filter(variant=self.variant).update(
            unit_buy_price=Decimal("999.00")
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, original_price)
        self.assertFalse(VariantPriceHistory.objects.exists())


class InventoryReportTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="report-admin", password="password")
        self.client.force_authenticate(self.user)
        self.pricing_service = InventoryPricingService()
        country = Country.objects.create(name="Report Country", code="RC", phone_code="+1")
        state = State.objects.create(name="Report State", country=country)
        city = City.objects.create(name="Report City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-report-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-REPORT",
            name="Report Warehouse",
            city=city,
            address="Report address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )
        self.normal, _ = InventoryStrategy.objects.update_or_create(
            code="normal", defaults={"name": "Normal"}
        )
        category_status = CategoryStatus.objects.create(name="report-active")
        product_status = ProductStatus.objects.create(name="report-pending")
        self.category_a = Category.objects.create(name="Report Category A", status=category_status)
        self.category_b = Category.objects.create(name="Report Category B", status=category_status)
        product_status_row = ProductStatus.objects.create(name="report-pending-row")
        product_a = Product.objects.create(name="Report Product A", status=product_status_row)
        product_a.categories.add(self.category_a)
        product_b = Product.objects.create(name="Report Product B", status=product_status_row)
        product_b.categories.add(self.category_b)
        self.variant_a = ProductVariants.objects.create(
            product=product_a,
            inventory_strategy=self.normal,
            sku="REPORT-A",
            combination_key="report-a",
            price="150.00",
        )
        self.variant_b = ProductVariants.objects.create(
            product=product_b,
            inventory_strategy=self.normal,
            sku="REPORT-B",
            combination_key="report-b",
            price="80.00",
        )

    def received_supply(self, *, variant=None, quantity=5, unit_buy_price="100.00",
                        costs=None, remaining=None, day=1):
        supply = InventorySupplyService().create_supply(
            variant=variant or self.variant_a,
            warehouse=self.warehouse,
            quantity=quantity,
            unit_buy_price=Decimal(unit_buy_price),
            supplied_at=timezone.make_aware(datetime(2026, 1, day)),
            costs=[{"type": "shipment", "amount": amount} for amount in (costs or [])],
        )
        if remaining is None:
            InventorySupplyService().receive_supply(supply)
        else:
            InventorySupply.objects.filter(id=supply.id).update(
                received_at=timezone.make_aware(datetime(2026, 1, day)),
                remaining_quantity=remaining,
            )
        return InventorySupply.objects.get(id=supply.id)

    def consumed_item(self, *, variant=None, quantity=2, stock=None):
        variant = variant or self.variant_a
        customer_status, _ = CustomerStatus.objects.get_or_create(
            name="active-consume", defaults={"title": "Active"}
        )
        self._customer_seq = getattr(self, "_customer_seq", 0) + 1
        customer = Customer.objects.create_user(
            phone=f"+98912000007{self._customer_seq}",
            first_name="Report",
            last_name="Tester",
            customer_code=f"CUS-REPORT-{self._customer_seq}",
            status=customer_status,
        )
        order_status, _ = OrderStatus.objects.get_or_create(
            name="payment_pending-consume", defaults={"fa_name": "pending"}
        )
        order = Order.objects.create(
            customer=customer,
            status=order_status,
            address_info={},
            subtotal=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("10.00"),
        )
        item = OrderItem.objects.create(
            order=order,
            variant=variant,
            sku=variant.sku,
            quantity=quantity,
            unit_price=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            final_price=Decimal("10.00"),
            inventory_strategy=variant.inventory_strategy,
        )
        stock = stock or WarehouseStock.objects.get(variant=variant, warehouse=self.warehouse)
        OrderItemReservation.objects.create(
            order_item=item,
            inventory_type="warehouse_stock",
            inventory_id=stock.id,
            quantity=quantity,
        )
        InventorySupplyService().consume_order_item(item)
        return item

    def test_summary_inventory_value_and_remaining_quantity(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", remaining=3, day=1)
        self.received_supply(
            variant=self.variant_b, quantity=4, unit_buy_price="200.00",
            costs=["40.00"], remaining=4, day=2,
        )
        response = self.client.get("/api/inventory/reports/summary")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        # 3*100 + 4*210 = 1140.
        self.assertEqual(data["inventory_cost_value"], "1140.00")
        self.assertEqual(data["remaining_supply_quantity"], 7)
        self.assertEqual(data["total_cogs"], "0.00")

    def test_summary_cogs_excludes_reversed_units(self):
        supply = self.received_supply(quantity=6, unit_buy_price="110.00", day=1)
        item = self.consumed_item(quantity=4)
        response = self.client.get("/api/inventory/reports/summary")
        self.assertEqual(response.data["data"]["total_cogs"], "440.00")

        # Reverse one unit: COGS must use net consumed quantities only.
        InventorySupplyService().reverse_order_item_consumption(item, quantity=1)
        refreshed = self.client.get("/api/inventory/reports/summary")
        self.assertEqual(refreshed.data["data"]["total_cogs"], "330.00")
        self.assertIsNotNone(supply.id)

    def test_summary_estimated_revenue_and_profit_use_suggested_pricing(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.consumed_item(quantity=2)
        self.client.patch(
            f"/api/inventory/variants/{self.variant_a.id}/pricing",
            {"cost_strategy": "latest", "expected_profit_percentage": "20.00"},
            format="json",
        )
        data = self.client.get("/api/inventory/reports/summary").data["data"]
        # Suggested price: landed 100 * 1.2 = 120; revenue 2 * 120; cogs 200.
        self.assertEqual(data["estimated_revenue"], "240.00")
        self.assertEqual(data["estimated_profit"], "40.00")

    def test_variant_report_totals_and_average_cost(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", remaining=3, day=1)
        supply_b = self.received_supply(
            variant=self.variant_b, quantity=4, unit_buy_price="200.00", day=1
        )
        item = self.consumed_item(variant=self.variant_b, quantity=3)
        response = self.client.get("/api/inventory/reports/variants")
        rows = {row["variant_id"]: row for row in response.data["data"]["results"]}
        row_a = rows[self.variant_a.id]
        self.assertEqual(row_a["remaining_quantity"], 3)
        self.assertEqual(row_a["inventory_cost_value"], "300.00")
        self.assertEqual(row_a["average_remaining_cost"], "100.00")
        self.assertEqual(row_a["total_consumed_quantity"], 0)
        self.assertEqual(row_a["total_cogs"], "0.00")
        self.assertEqual(row_a["current_price"], "150.00")
        self.assertIsNone(row_a["suggested_price"])
        row_b = rows[self.variant_b.id]
        self.assertEqual(row_b["inventory_cost_value"], "200.00")
        self.assertEqual(row_b["average_remaining_cost"], "200.00")
        self.assertEqual(row_b["total_consumed_quantity"], 3)
        self.assertEqual(row_b["total_cogs"], "600.00")

    def test_variant_report_filters_search_category_strategy_and_ordering(self):
        self.configure_pricing(self.variant_a, strategy="latest")
        self.configure_pricing(self.variant_b, strategy="fifo_next")
        search = self.client.get("/api/inventory/reports/variants", {"search": "REPORT-A"})
        self.assertEqual(search.data["data"]["count"], 1)
        by_category = self.client.get(
            "/api/inventory/reports/variants", {"category_id": self.category_b.id}
        )
        self.assertEqual(by_category.data["data"]["count"], 1)
        self.assertEqual(by_category.data["data"]["results"][0]["sku"], "REPORT-B")
        by_strategy = self.client.get(
            "/api/inventory/reports/variants", {"strategy": "fifo_next"}
        )
        self.assertEqual(by_strategy.data["data"]["count"], 1)
        ordered = self.client.get(
            "/api/inventory/reports/variants", {"ordering": "-current_price"}
        )
        prices = [Decimal(r["current_price"]) for r in ordered.data["data"]["results"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def configure_pricing(self, variant, *, strategy):
        response = self.client.patch(
            f"/api/inventory/variants/{variant.id}/pricing",
            {"cost_strategy": strategy},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_supply_report_rows_with_landed_values(self):
        supply = self.received_supply(
            quantity=5, unit_buy_price="100.00", costs=["50.00"],
            remaining=2, day=3,
        )
        response = self.client.get("/api/inventory/reports/supplies")
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["supply_id"], supply.id)
        self.assertEqual(row["variant"]["sku"], "REPORT-A")
        self.assertEqual(row["warehouse"]["code"], "WH-REPORT")
        self.assertEqual(row["original_quantity"], 5)
        self.assertEqual(row["remaining_quantity"], 2)
        self.assertEqual(row["consumed_quantity"], 3)
        self.assertEqual(row["unit_buy_price"], "100.00")
        self.assertEqual(row["landed_unit_cost"], "110.00")
        self.assertEqual(row["original_cost_value"], "550.00")
        self.assertEqual(row["remaining_cost_value"], "220.00")
        self.assertEqual(row["consumed_cost_value"], "330.00")

    def test_supply_report_multiple_batches_and_filters(self):
        self.received_supply(quantity=5, unit_buy_price="100.00", day=1)
        self.received_supply(
            variant=self.variant_b, quantity=4, unit_buy_price="70.00", day=2
        )
        listed = self.client.get("/api/inventory/reports/supplies")
        self.assertEqual(listed.data["data"]["count"], 2)
        newest_first = [row["original_quantity"] for row in listed.data["data"]["results"]]
        self.assertEqual(newest_first, [4, 5])
        searched = self.client.get("/api/inventory/reports/supplies", {"search": "REPORT-B"})
        self.assertEqual(searched.data["data"]["count"], 1)

    def test_unreceived_supplies_are_excluded_from_reports(self):
        InventorySupplyService().create_supply(
            variant=self.variant_a,
            warehouse=self.warehouse,
            quantity=99,
            unit_buy_price=Decimal("500.00"),
            supplied_at=timezone.make_aware(datetime(2026, 6, 1)),
        )
        summary = self.client.get("/api/inventory/reports/summary").data["data"]
        self.assertEqual(summary["inventory_cost_value"], "0.00")
        self.assertEqual(summary["remaining_supply_quantity"], 0)
        supplies = self.client.get("/api/inventory/reports/supplies").data["data"]
        self.assertEqual(supplies["count"], 0)
        variants = self.client.get("/api/inventory/reports/variants").data["data"]
        for row in variants["results"]:
            self.assertEqual(row["inventory_cost_value"], "0.00")

    def test_report_decimal_accuracy_with_repeating_costs(self):
        self.received_supply(quantity=3, unit_buy_price="33.33", costs=["0.01"], remaining=2, day=1)
        data = self.client.get("/api/inventory/reports/summary").data["data"]
        # landed unit cost is exactly 100/3; value is 2 * 100/3 quantized once.
        self.assertEqual(data["inventory_cost_value"], "66.67")
        variants = self.client.get("/api/inventory/reports/variants").data["data"]
        row = variants["results"][0]
        self.assertEqual(row["inventory_cost_value"], "66.67")
        self.assertEqual(row["average_remaining_cost"], "33.33")
        supplies = self.client.get("/api/inventory/reports/supplies").data["data"]["results"]
        self.assertEqual(supplies[0]["landed_unit_cost"], "33.33")
        self.assertEqual(supplies[0]["remaining_cost_value"], "66.67")

    def test_report_permissions_are_enforced(self):
        staff = User.objects.create_user(username="report-staff", is_staff=True)
        urls = (
            "/api/inventory/reports/summary",
            "/api/inventory/reports/variants",
            "/api/inventory/reports/supplies",
        )
        self.client.force_authenticate(None)
        for url in urls:
            self.assertIn(self.client.get(url).status_code, (401, 403))
        self.client.force_authenticate(staff)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_inventory"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)
