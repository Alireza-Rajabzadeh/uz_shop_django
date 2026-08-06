from django.contrib.auth.models import Permission, User
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
from domains.inventory.models import (
    InventoryStrategy,
    SerializedStock,
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)
from domains.location.models import City, Country, State


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
