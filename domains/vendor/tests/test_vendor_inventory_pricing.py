from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
)
from domains.inventory.models import Inventory, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.inventory import VendorInventoryOverviewView
from domains.vendor.views.products import VendorProductVariantDetailView


class VendorInventoryPricingTests(TestCase):
    """Regression coverage for the two vendor inventory write/read defects.

    The overview endpoint used InventoryPricingService.calculate_discounted_price,
    which does not exist, so listing inventory raised AttributeError (HTTP 500).
    The catalog variant write serializer omitted min_stock, so the threshold the
    vendor panel submits was silently dropped instead of persisted.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334455",
            password="pass1234",
            first_name="Inventory",
            last_name="Vendor",
            national_id="1122334455",
            status=self.vendor_status,
        )

        # Exactly one default warehouse, as required by get_default_warehouse().
        # Warehouse defaults are unique per business, so the business must exist
        # before the warehouse does.
        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Overview Phones", status=category_status)
        self.business = BusinessProfile.objects.create(
            id=9999,
            vendor=self.vendor,
            business_name="Overview Business",
            display_name="Overview Business",
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)

        country = Country.objects.create(name="Overview Country", code="OC", phone_code="+1")
        state = State.objects.create(name="Overview State", country=country)
        city = City.objects.create(name="Overview City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-OVERVIEW",
            name="Overview Warehouse",
            business=self.business,
            city=city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )

        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Overview Product", status=product_status)
        self.product.categories.add(self.category)
        self.variant_status = ProductVariantStatus.objects.create(name="active")
        self.variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_status,
            sku="OVW-SKU-1",
            combination_key="BLK-128",
        )

    def test_inventory_overview_reports_discounted_price(self):
        """GET /vendor/overview must price the row instead of raising."""
        BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
            discount_type="fixed",
            discount_value=Decimal("10.00"),
        )

        request = self.factory.get("/vendor/inventory/overview")
        force_authenticate(request, user=self.vendor)
        response = VendorInventoryOverviewView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual(len(rows), 1)

        row = rows[0]
        self.assertEqual(row["price"], "100.00")
        self.assertIsNotNone(row["discounted_price"])
        self.assertEqual(Decimal(row["discounted_price"]), Decimal("90.00"))

    def test_inventory_overview_survives_variant_without_offer(self):
        """No offer means no discount, not an exception."""
        request = self.factory.get("/vendor/inventory/overview")
        force_authenticate(request, user=self.vendor)
        response = VendorInventoryOverviewView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        row = response.data["data"][0]
        self.assertIsNone(row["price"])
        self.assertIsNone(row["discounted_price"])

    def test_inventory_overview_ignores_unowned_default_warehouse(self):
        """Defaults are unique per business, so an unrelated default must not
        make the lookup ambiguous and fail the whole listing."""
        Warehouse.objects.create(
            code="WH-ORPHAN",
            name="Unowned Warehouse",
            business=None,
            city=self.warehouse.city,
            address="Orphan address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )

        request = self.factory.get("/vendor/inventory/overview")
        force_authenticate(request, user=self.vendor)
        response = VendorInventoryOverviewView.as_view()(request)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["data"]), 1)

    def test_inventory_overview_reports_missing_default_as_400(self):
        """A service-level rule must surface as a 400, not a 500 traceback."""
        self.warehouse.delete()

        request = self.factory.get("/vendor/inventory/overview")
        force_authenticate(request, user=self.vendor)
        response = VendorInventoryOverviewView.as_view()(request)

        self.assertEqual(response.status_code, 400)

    def test_variant_patch_persists_min_stock(self):
        """PATCH /vendor/variants/:id stores the submitted min_stock threshold."""
        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}",
            {
                "inventory": {
                    "quantity": 10,
                    "sellable": 8,
                    "min_stock": 5,
                }
            },
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantDetailView.as_view()(
            request, variant_id=self.variant.id
        )

        self.assertEqual(response.status_code, 200, response.data)

        stock = Inventory.objects.get(variant=self.variant, warehouse=self.warehouse)
        self.assertEqual(stock.quantity, 10)
        self.assertEqual(stock.sellable, 8)
        self.assertEqual(stock.min_stock, 5)

    def test_variant_patch_without_min_stock_keeps_existing_threshold(self):
        """An omitted min_stock keeps the stored value instead of resetting to 0."""
        Inventory.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.variant,
            inventory_type_id=1,
            quantity=4,
            sellable=4,
            reserved=0,
            min_stock=7,
        )

        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}",
            {"inventory": {"quantity": 4, "sellable": 3}},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantDetailView.as_view()(
            request, variant_id=self.variant.id
        )

        self.assertEqual(response.status_code, 200, response.data)
        stock = Inventory.objects.get(variant=self.variant, warehouse=self.warehouse)
        self.assertEqual(stock.sellable, 3)
        self.assertEqual(stock.min_stock, 7)
