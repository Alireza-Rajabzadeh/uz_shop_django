from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariants, VariantAttribute, VariantOption
from domains.inventory.models import Warehouse, WarehouseStatus
from domains.location.models import City, Country, State


class InventoryAPITests(APITestCase):
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
        category_status = CategoryStatus.objects.create(name="inventory-active")
        product_status = ProductStatus.objects.create(name="inventory-pending")
        category = Category.objects.create(name="Inventory Category", status=category_status)
        self.product = Product.objects.create(name="Inventory Product", status=product_status)
        self.product.categories.add(category)
        self.attribute = VariantAttribute.objects.create(name="Inventory Color")
        self.option_a = VariantOption.objects.create(attribute=self.attribute, name="Black", sku_code="INVBLK")
        self.option_b = VariantOption.objects.create(attribute=self.attribute, name="White", sku_code="INVWHT")

    def payload(self, *, serialized=False, option=None):
        data = {
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

    def test_create_variant_persists_inventory_and_reserved_stock(self):
        response = self.create_variant()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["total_item_count"], 10)
        self.assertEqual(response.data["data"]["sellable_item_count"], 8)

        variant = ProductVariants.objects.get()
        stock = variant.inventories.get(warehouse=self.warehouse)
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

    def test_permission_checks_are_enforced_for_inventory_views_and_updates(self):
        self.assertEqual(self.create_variant().status_code, 201)
        variant = ProductVariants.objects.get()

        staff = User.objects.create_user(username="inventory-staff", is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/inventory/variants").status_code, 403)

        view_permission = Permission.objects.filter(codename="view_inventory").order_by("id").first()
        staff.user_permissions.add(view_permission)
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

        adjust_permission = Permission.objects.filter(codename="adjust_stock").order_by("id").first()
        staff.user_permissions.add(adjust_permission)
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

    def test_duplicate_serial_numbers_are_rejected_globally(self):
        response = self.create_variant(serialized=True)
        print("SERIALIZED CREATE RESPONSE", response.status_code, response.data)
        self.assertEqual(response.status_code, 201)

        payload = self.payload(serialized=True, option=self.option_b)
        payload["serial_items"][0]["serial_number"] = "sn 001"
        payload["serial_items"][1]["serial_number"] = "SN-OTHER"

        response = self.client.post(
            f"/api/catalog/products/{self.product.id}/variants",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProductVariants.objects.count(), 1)

    def test_default_warehouse_protection_is_enforced(self):
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

        self.assertEqual(self.create_variant().status_code, 201)
        response = self.client.delete(f"/api/inventory/warehouses/{self.warehouse.id}")
        self.assertEqual(response.status_code, 400)
