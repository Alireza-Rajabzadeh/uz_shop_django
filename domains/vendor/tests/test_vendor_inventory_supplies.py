from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
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
from domains.inventory.models import (
    InventorySupply,
    InventorySupplyCost,
    Warehouse,
    WarehouseStatus,
)
from domains.location.models import City, Country, State
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.inventory import VendorSupplyOverviewView


class VendorSupplyOverviewTests(TestCase):
    """GET /vendor/supplies/overview feeds the panel's supplies page.

    The view used to query `InventorySupply` directly, so rows arrived
    without the `extra_cost_total` annotation that `serialize_supply_row`
    reads and every call raised AttributeError (HTTP 500); the page hid the
    failure as an empty list, which read as "there is no API". It also
    capped the result at 50 and joined the business's categories, which
    dropped supplies whose product left a category and duplicated products
    sitting in two of them. The overview must return every supply the
    business owns, once each.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334466",
            password="pass1234",
            first_name="Supply",
            last_name="Vendor",
            national_id="1122334466",
            status=self.vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09123334477",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="1122334477",
            status=self.vendor_status,
        )

        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Supply Phones", status=category_status)
        self.category_status = category_status
        self.business = BusinessProfile.objects.create(
            id=9997,
            vendor=self.vendor,
            business_name="Supply Business",
            display_name="Supply Business",
        )
        self.other_business = BusinessProfile.objects.create(
            id=9998,
            vendor=self.other_vendor,
            business_name="Other Supply Business",
            display_name="Other Supply Business",
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)

        country = Country.objects.create(name="Supply Country", code="SP", phone_code="+1")
        state = State.objects.create(name="Supply State", country=country)
        city = City.objects.create(name="Supply City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="available-for-tests")
        self.warehouse = Warehouse.objects.create(
            code="WH-SUPPLY",
            name="Supply Warehouse",
            business=self.business,
            city=city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )

        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Supply Product", status=product_status)
        self.product.categories.add(self.category)
        variant_status = ProductVariantStatus.objects.create(name="active")
        self.variant = ProductVariants.objects.create(
            product=self.product,
            status=variant_status,
            sku="SUP-SKU-1",
            combination_key="BLK-64",
        )

    def _get(self):
        request = self.factory.get("/vendor/supplies/overview")
        force_authenticate(request, user=self.vendor)
        return VendorSupplyOverviewView.as_view()(request)

    def _supply(self, *, business_marker=None, supplied_at=None):
        business = self.business if business_marker is None else business_marker
        return InventorySupply.objects.create(
            business=business,
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=4,
            remaining_quantity=4,
            unit_buy_price="100.00",
            supplied_at=supplied_at or timezone.now(),
        )

    def test_overview_returns_every_supply_owned_by_the_business(self):
        """No [:50] cap: the page renders the full supply history, newest first."""
        now = timezone.now()
        InventorySupply.objects.bulk_create(
            [
                InventorySupply(
                    business=self.business,
                    variant=self.variant,
                    warehouse=self.warehouse,
                    quantity=1,
                    remaining_quantity=1,
                    unit_buy_price="100.00",
                    supplied_at=now - timedelta(days=offset),
                )
                for offset in range(55)
            ]
        )

        response = self._get()

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["data"]
        self.assertEqual(len(rows), 55)
        # Newest first, matching the per-variant supply list.
        supplied = [row["supplied_at"] for row in rows]
        self.assertEqual(supplied, sorted(supplied, reverse=True))

    def test_overview_serializes_landed_costs(self):
        """Rows must carry the annotated extra cost, not raise AttributeError."""
        supply = self._supply()
        InventorySupplyCost.objects.create(
            supply=supply, type="shipment", amount="25.50", description="Freight"
        )

        response = self._get()

        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["data"][0]
        self.assertEqual(Decimal(row["base_cost_total"]), Decimal("400.00"))
        self.assertEqual(Decimal(row["extra_cost_total"]), Decimal("25.50"))
        self.assertEqual(Decimal(row["landed_cost_total"]), Decimal("425.50"))
        self.assertFalse(row["is_received"])

    def test_overview_excludes_supplies_owned_by_other_businesses(self):
        own = self._supply()
        InventorySupply.objects.create(
            business=self.other_business,
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=2,
            remaining_quantity=2,
            unit_buy_price="50.00",
            supplied_at=timezone.now(),
        )
        # Legacy rows created through the admin tier never got a business.
        InventorySupply.objects.create(
            business=None,
            variant=self.variant,
            warehouse=self.warehouse,
            quantity=2,
            remaining_quantity=2,
            unit_buy_price="50.00",
            supplied_at=timezone.now(),
        )

        response = self._get()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data["data"]], [own.id])

    def test_overview_does_not_duplicate_products_in_several_categories(self):
        """A category join would double the row; business_id scoping must not."""
        second_category = Category.objects.create(
            name="Supply Accessories", status=self.category_status
        )
        BusinessCategory.objects.create(business=self.business, category=second_category)
        self.product.categories.add(second_category)
        supply = self._supply()

        response = self._get()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["id"] for row in response.data["data"]], [supply.id])
