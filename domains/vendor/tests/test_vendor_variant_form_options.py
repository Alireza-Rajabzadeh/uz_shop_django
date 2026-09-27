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
from domains.inventory.models import Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.products import VendorProductVariantFormOptionsView


class VendorVariantFormOptionsTests(TestCase):
    """The stock type selector options must be inventory types.

    The endpoint served InventoryPricingService.get_strategies(), which returns
    cost-basis pricing strategies (latest / weighted_average / fifo_next). The
    selector binds its value to the variant's inventory type code
    (normal / serialized), so no option ever matched the current value and
    picking one could not express a real inventory type.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334456",
            password="pass1234",
            first_name="Form",
            last_name="Options",
            national_id="1122334456",
            status=self.vendor_status,
        )

        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Form Options Phones", status=category_status)
        self.business = BusinessProfile.objects.create(
            id=9998,
            vendor=self.vendor,
            business_name="Form Options Business",
            display_name="Form Options Business",
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)

        country = Country.objects.create(name="FO Country", code="FC", phone_code="+1")
        state = State.objects.create(name="FO State", country=country)
        city = City.objects.create(name="FO City", state=state)
        warehouse_status = WarehouseStatus.objects.create(name="available-for-form-options")
        self.warehouse = Warehouse.objects.create(
            code="WH-FORMOPT",
            name="Form Options Warehouse",
            business=self.business,
            city=city,
            address="Test address",
            lat="0",
            lng="0",
            is_default=True,
            status=warehouse_status,
        )

        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Form Options Product", status=product_status)
        self.product.categories.add(self.category)
        variant_status = ProductVariantStatus.objects.create(name="active")
        self.variant = ProductVariants.objects.create(
            product=self.product,
            status=variant_status,
            sku="FORMOPT-SKU-1",
            combination_key="BLK-256",
        )

    def _get(self):
        request = self.factory.get(f"/vendor/products/{self.product.id}/variant-form-options")
        force_authenticate(request, user=self.vendor)
        return VendorProductVariantFormOptionsView.as_view()(
            request, product_id=self.product.id
        )

    def test_form_options_serve_inventory_types(self):
        """normal / serialized, each with a stable id for the option key."""
        response = self._get()

        self.assertEqual(response.status_code, 200)
        options = response.data["data"]["inventory_strategies"]

        self.assertEqual({item["code"] for item in options}, {"normal", "serialized"})
        for item in options:
            self.assertIsInstance(item["id"], int)
            self.assertTrue(item["name"])
            self.assertTrue(item["fa_name"])

    def test_form_options_exclude_cost_strategies(self):
        """Cost strategies belong to pricing, not to the stock type selector."""
        response = self._get()

        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.data["data"]["inventory_strategies"]}

        self.assertFalse(codes & {"latest", "weighted_average", "fifo_next"})

    def test_form_options_scope_the_warehouse_to_the_business(self):
        """An unrelated default warehouse must not make the lookup ambiguous."""
        Warehouse.objects.create(
            code="WH-FORMOPT-ORPHAN",
            name="Unowned Warehouse",
            business=None,
            city=self.warehouse.city,
            address="Orphan address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse.status,
        )

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["default_warehouse"]["code"], "WH-FORMOPT")
