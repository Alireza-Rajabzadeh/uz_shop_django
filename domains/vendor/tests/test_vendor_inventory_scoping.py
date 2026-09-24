from rest_framework.test import APITestCase

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
)
from domains.inventory.models import (
    Inventory,
    InventorySupply,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus


class VendorInventoryBusinessScopeAPITests(APITestCase):
    """Vendor inventory reads must report only the requesting business' stock."""

    def setUp(self):
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334455",
            password="pass1234",
            first_name="Scoped",
            last_name="Vendor",
            national_id="1112223334",
            status=self.vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09127778899",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="4445556667",
            status=self.vendor_status,
        )
        self.business = BusinessProfile.objects.create(
            id=201,
            vendor=self.vendor,
            business_name="Scoped Vendor Business",
            display_name="Scoped Vendor",
        )
        self.other_business = BusinessProfile.objects.create(
            id=202,
            vendor=self.other_vendor,
            business_name="Unrelated Business",
            display_name="Unrelated Vendor",
        )

        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Scoped Category",
            status=self.category_status,
        )
        BusinessCategory.objects.create(
            business=self.business,
            category=self.category,
        )
        BusinessCategory.objects.create(
            business=self.other_business,
            category=self.category,
        )

        self.product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(
            name="Scoped Product",
            status=self.product_status,
        )
        self.product.categories.add(self.category)
        self.variant = ProductVariants.objects.create(
            product=self.product,
            sku="SCOPED-STOCK-SKU",
            combination_key="scoped-stock-sku",
        )

        country = Country.objects.create(name="Scope Country", code="SC", phone_code="+1")
        state = State.objects.create(name="Scope State", country=country)
        city = City.objects.create(name="Scope City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available")

        self.warehouse = Warehouse.objects.create(
            code="WH-SCOPED-A",
            name="Scoped Warehouse A",
            business=self.business,
            city=city,
            address="Scoped address A",
            lat="0",
            lng="0",
            status=self.warehouse_status,
            is_default=True,
        )
        self.other_warehouse = Warehouse.objects.create(
            code="WH-SCOPED-B",
            name="Scoped Warehouse B",
            business=self.other_business,
            city=city,
            address="Scoped address B",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )
        self.global_warehouse = Warehouse.objects.create(
            code="WH-SCOPED-GLOBAL",
            name="Scoped Global Warehouse",
            city=city,
            address="Scoped global address",
            lat="0",
            lng="0",
            status=self.warehouse_status,
        )
        self.client.force_authenticate(self.vendor)

    def _add_stock(self, *, business, warehouse, quantity, sellable, reserved=0):
        return Inventory.objects.create(
            business=business,
            warehouse=warehouse,
            variant=self.variant,
            quantity=quantity,
            sellable=sellable,
            reserved=reserved,
            min_stock=0,
        )

    def _add_supply(self, *, business, warehouse, quantity):
        return InventorySupply.objects.create(
            business=business,
            variant=self.variant,
            warehouse=warehouse,
            quantity=quantity,
            unit_buy_price="100.00",
            supplied_at="2026-01-01T00:00:00Z",
        )

    def test_inventory_detail_sums_only_current_business_stock(self):
        # Two rows owned by the requesting business must be summed together.
        self._add_stock(business=self.business, warehouse=self.warehouse, quantity=1, sellable=0)
        self._add_stock(
            business=self.business,
            warehouse=self.global_warehouse,
            quantity=30,
            sellable=0,
        )
        # Another business' stock must never leak into the vendor's numbers.
        self._add_stock(
            business=self.other_business,
            warehouse=self.other_warehouse,
            quantity=60,
            sellable=17,
        )

        response = self.client.get(
            f"/api/vendor/variants/{self.variant.id}/inventory"
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["total_item_count"], 31)
        self.assertEqual(data["sellable_item_count"], 0)
        self.assertEqual(data["available_item_count"], 0)

    def test_inventory_detail_warehouse_block_uses_business_warehouse(self):
        self._add_stock(business=self.business, warehouse=self.warehouse, quantity=4, sellable=2)
        self._add_stock(
            business=self.other_business,
            warehouse=self.other_warehouse,
            quantity=60,
            sellable=17,
        )

        response = self.client.get(
            f"/api/vendor/variants/{self.variant.id}/inventory"
        )

        self.assertEqual(response.status_code, 200)
        inventory = response.data["data"]["inventory"]
        self.assertEqual(inventory["warehouse"]["code"], self.warehouse.code)
        self.assertEqual(inventory["quantity"], 4)
        self.assertEqual(inventory["sellable"], 2)

    def test_inventory_detail_supply_total_excludes_other_and_unassigned(self):
        self._add_supply(business=self.business, warehouse=self.warehouse, quantity=5)
        self._add_supply(
            business=self.other_business,
            warehouse=self.other_warehouse,
            quantity=7,
        )
        self._add_supply(business=None, warehouse=self.global_warehouse, quantity=9)

        response = self.client.get(
            f"/api/vendor/variants/{self.variant.id}/inventory"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["total_supply_quantity"], 5)

    def test_inventory_overview_reports_business_scoped_stock(self):
        self._add_stock(business=self.business, warehouse=self.warehouse, quantity=2, sellable=1)
        self._add_stock(
            business=self.other_business,
            warehouse=self.other_warehouse,
            quantity=60,
            sellable=17,
        )

        response = self.client.get("/api/vendor/inventory/overview")

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_stock"], 2)
        self.assertEqual(rows[0]["sellable_stock"], 1)
        self.assertEqual(rows[0]["available_stock"], 1)

    def test_inventory_detail_is_zero_without_business_stock(self):
        self._add_stock(
            business=self.other_business,
            warehouse=self.other_warehouse,
            quantity=60,
            sellable=17,
        )

        response = self.client.get(
            f"/api/vendor/variants/{self.variant.id}/inventory"
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["total_item_count"], 0)
        self.assertEqual(data["sellable_item_count"], 0)
        self.assertEqual(data["available_item_count"], 0)
        self.assertEqual(data["inventory"]["quantity"], 0)
