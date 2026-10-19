from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from domains.business.models import BusinessProfile
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariantStatus, ProductVariants, VariantAttribute, VariantOption
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State


class InventoryAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="inventory-admin", password="password")
        self.client.force_authenticate(self.user)
        country = Country.objects.create(name="Inventory Country", code="IC", phone_code="+1")
        state = State.objects.create(name="Inventory State", country=country)
        self.city = City.objects.create(name="Inventory City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-tests")
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={"business_name": "Inventory Business", "display_name": "Inventory Business"},
        )
        self.warehouse = Warehouse.objects.create(
            code="WH-TEST",
            name="Default Test Warehouse",
            business=self.business,
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
        self.assertEqual(
            self.client.get(f"/api/inventory/variants?business_id={self.business.id}").status_code,
            403,
        )

        view_permission = Permission.objects.filter(codename="view_inventory").order_by("id").first()
        staff.user_permissions.add(view_permission)
        staff = User.objects.get(pk=staff.pk)
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(f"/api/inventory/variants?business_id={self.business.id}").status_code,
            200,
        )

        self.assertEqual(
            self.client.patch(
                f"/api/inventory/variants/{variant.id}?business_id={self.business.id}",
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
                f"/api/inventory/variants/{variant.id}?business_id={self.business.id}",
                {"inventory": {"quantity": 10, "sellable": 8, "min_stock": 0}},
                format="json",
            ).status_code,
            200,
        )

    def test_duplicate_serial_numbers_are_rejected_globally(self):
        response = self.create_variant(serialized=True)
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
        created = self.client.post(
            f"/api/inventory/warehouses?business_id={self.business.id}",
            payload,
            format="json",
        )
        self.assertEqual(created.status_code, 201)

        self.assertEqual(self.create_variant().status_code, 201)
        response = self.client.delete(
            f"/api/inventory/warehouses/{self.warehouse.id}?business_id={self.business.id}"
        )
        self.assertEqual(response.status_code, 400)


class InventoryRecordScopeTests(APITestCase):
    """Inventory lists read the scope's records, not the whole catalog.

    A variant enters a scope only once an ``Inventory`` row exists for it (a
    received supply or a stock adjustment), so an unstocked variant stays out of
    the list. The supply form therefore needs a separate, records-free options
    source to open that first supply.
    """

    def setUp(self):
        self.user = User.objects.create_superuser(username="inventory-scope", password="password")
        self.client.force_authenticate(self.user)
        country = Country.objects.create(name="Scope Country", code="SC", phone_code="+1")
        state = State.objects.create(name="Scope State", country=country)
        city = City.objects.create(name="Scope City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="scope-available")
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={"business_name": "Scope Business", "display_name": "Scope Business"},
        )
        self.warehouse = Warehouse.objects.create(
            code="WH-SCOPE",
            name="Scope Warehouse",
            business=self.business,
            city=city,
            address="Scope address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="scope-active")
        product_status = ProductStatus.objects.create(name="scope-pending")
        variant_status = ProductVariantStatus.objects.create(name="scope-variant")
        category = Category.objects.create(name="Scope Category", status=category_status)
        self.product = Product.objects.create(name="Scope Product", status=product_status)
        self.product.categories.add(category)
        self.stocked = ProductVariants.objects.create(
            product=self.product,
            status=variant_status,
            sku="SCOPE-STOCKED",
            combination_key="S-BLK",
        )
        self.unstocked = ProductVariants.objects.create(
            product=self.product,
            status=variant_status,
            sku="SCOPE-UNSTOCKED",
            combination_key="S-WHT",
        )
        Inventory.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.stocked,
            inventory_type_id=1,
            quantity=5,
            sellable=5,
            reserved=0,
            min_stock=0,
        )

    def test_variant_list_returns_only_stocked_variants(self):
        response = self.client.get(f"/api/inventory/variants?business_id={self.business.id}")

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["variant"] for row in response.data["data"]["results"]]
        self.assertEqual(ids, [self.stocked.id])

    def test_variant_list_without_a_warehouse_is_empty_not_an_error(self):
        Inventory.objects.all().delete()
        self.warehouse.delete()

        response = self.client.get(f"/api/inventory/variants?business_id={self.business.id}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["count"], 0)

    def test_variant_options_offer_unstocked_variants(self):
        response = self.client.get("/api/inventory/variant-options")

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["id"] for row in response.data["data"]["results"]]
        self.assertIn(self.stocked.id, ids)
        self.assertIn(self.unstocked.id, ids)

    def test_variant_options_search_matches_sku(self):
        response = self.client.get("/api/inventory/variant-options?search=SCOPE-UNSTOCKED")

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["id"] for row in response.data["data"]["results"]]
        self.assertEqual(ids, [self.unstocked.id])

    def test_pricing_list_covers_only_stocked_variants(self):
        response = self.client.get(f"/api/inventory/pricing?business_id={self.business.id}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_report_variant_list_covers_only_stocked_variants(self):
        response = self.client.get(
            f"/api/inventory/reports/variants?business_id={self.business.id}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["count"], 1)
