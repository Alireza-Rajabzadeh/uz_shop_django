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
from domains.inventory.models import Inventory, InventorySupply, Warehouse, WarehouseStatus
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.inventory import VendorInventoryOverviewView, VendorVariantPricingView
from domains.vendor.views.products import VendorProductVariantDetailView


class VendorInventoryPricingTests(TestCase):
    """Regression coverage for vendor inventory write/read defects.

    The overview endpoint used InventoryPricingService.calculate_discounted_price,
    which does not exist, so listing inventory raised AttributeError (HTTP 500).
    The catalog variant write serializer omitted min_stock, so the threshold the
    vendor panel submits was silently dropped instead of persisted.

    The class also covers the pricing-configuration split: saving a cost
    strategy must work without a marketplace offer, and calculating a price
    must work without any saved configuration at all.
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

    # ─────────────────── pricing configuration vs. offers ───────────────────

    def _supply(self, *, unit_buy_price="100.00", quantity=10):
        """A fully received supply batch so cost calculation has input."""
        supplied_at = timezone.now() - timedelta(hours=1)
        return InventorySupply.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.variant,
            quantity=quantity,
            remaining_quantity=quantity,
            unit_buy_price=Decimal(unit_buy_price),
            supplied_at=supplied_at,
            received_at=supplied_at,
        )

    def _patch_pricing(self, payload):
        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}/pricing", payload, format="json"
        )
        force_authenticate(request, user=self.vendor)
        return VendorVariantPricingView.as_view()(
            request, variant_id=self.variant.id
        )

    def _get_pricing(self, query=None):
        request = self.factory.get(
            f"/vendor/variants/{self.variant.id}/pricing", query or {}
        )
        force_authenticate(request, user=self.vendor)
        return VendorVariantPricingView.as_view()(
            request, variant_id=self.variant.id
        )

    def test_saving_strategy_without_offer_creates_inactive_draft(self):
        """Saving strategy must not demand a marketplace offer first."""
        response = self._patch_pricing({
            "cost_strategy": "weighted_average",
            "expected_profit_percentage": "25",
        })

        self.assertEqual(response.status_code, 200, response.data)
        offer = BusinessOffer.objects.get(variant=self.variant)
        self.assertEqual(offer.business, self.business)
        # Creating config must never publish the variant.
        self.assertFalse(offer.is_active)
        self.assertEqual(str(offer.price), "0.00")
        self.assertEqual(offer.cost_strategy.code, "weighted_average")
        self.assertEqual(offer.expected_profit_percentage, Decimal("25.00"))

        data = response.data["data"]
        self.assertEqual(data["cost_strategy"], "weighted_average")
        self.assertEqual(data["expected_profit_percentage"], "25.00")

    def test_saving_strategy_twice_updates_the_same_draft(self):
        """The draft is a normal config row: repeated saves must not fork it."""
        first = self._patch_pricing({
            "cost_strategy": "fifo_next",
            "expected_profit_percentage": "10",
        })
        self.assertEqual(first.status_code, 200, first.data)

        second = self._patch_pricing({"expected_profit_percentage": "20"})
        self.assertEqual(second.status_code, 200, second.data)

        offers = BusinessOffer.objects.filter(variant=self.variant)
        self.assertEqual(offers.count(), 1)
        offer = offers.get()
        self.assertEqual(offer.cost_strategy.code, "fifo_next")
        self.assertEqual(offer.expected_profit_percentage, Decimal("20.00"))
        self.assertFalse(offer.is_active)

    def test_pricing_overview_derives_costs_from_supplies_without_config(self):
        """Cost cards are supply-derived, so they render with no offer."""
        self._supply(unit_buy_price="100.00", quantity=10)

        response = self._get_pricing()

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertIsNone(data["cost_strategy"])
        self.assertIsNone(data["cost_basis"])
        self.assertIsNone(data["suggested_price"])
        self.assertEqual(data["latest_cost"], "100.00")
        self.assertEqual(data["weighted_average_cost"], "100.00")
        self.assertEqual(data["fifo_next_cost"], "100.00")
        self.assertEqual(data["total_remaining_supply_quantity"], 10)
        # A read must never create an offer.
        self.assertFalse(BusinessOffer.objects.filter(variant=self.variant).exists())

    def test_pricing_overview_calculates_with_unsaved_strategy(self):
        """Query params are unsaved overrides for the calculate action."""
        self._supply(unit_buy_price="100.00", quantity=10)

        response = self._get_pricing({
            "cost_strategy": "latest",
            "expected_profit_percentage": "25",
        })

        self.assertEqual(response.status_code, 200, response.data)
        data = response.data["data"]
        self.assertEqual(data["cost_strategy"], "latest")
        self.assertEqual(data["cost_basis"], "100.00")
        self.assertEqual(data["suggested_price"], "125.00")
        self.assertFalse(BusinessOffer.objects.filter(variant=self.variant).exists())

    def test_pricing_overview_rejects_unknown_strategy(self):
        response = self._get_pricing({"cost_strategy": "not-a-strategy"})

        self.assertEqual(response.status_code, 400)

    def test_variant_patch_price_creates_draft_offer_and_stores_strategy(self):
        """Applying a price persists price + strategy together, still unlisted."""
        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}",
            {
                "price": "150.00",
                "cost_strategy": "fifo_next",
                "expected_profit_percentage": "20",
            },
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantDetailView.as_view()(
            request, variant_id=self.variant.id
        )

        self.assertEqual(response.status_code, 200, response.data)
        offer = BusinessOffer.objects.get(business=self.business, variant=self.variant)
        self.assertEqual(str(offer.price), "150.00")
        self.assertEqual(offer.cost_strategy.code, "fifo_next")
        self.assertEqual(offer.expected_profit_percentage, Decimal("20.00"))
        # Pricing the variant is not a listing decision.
        self.assertFalse(offer.is_active)

        detail_request = self.factory.get(f"/vendor/variants/{self.variant.id}")
        force_authenticate(detail_request, user=self.vendor)
        detail = VendorProductVariantDetailView.as_view()(
            detail_request, variant_id=self.variant.id
        )
        self.assertEqual(
            detail.data["data"]["marketplace_offer_status"], "inactive"
        )

    def test_variant_patch_updates_the_draft_created_by_a_strategy_save(self):
        """Price + strategy must land on the existing draft, not a second row."""
        created = self._patch_pricing({
            "cost_strategy": "latest",
            "expected_profit_percentage": "10",
        })
        self.assertEqual(created.status_code, 200, created.data)

        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}",
            {"price": "250.00", "expected_profit_percentage": "15"},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantDetailView.as_view()(
            request, variant_id=self.variant.id
        )

        self.assertEqual(response.status_code, 200, response.data)
        offers = BusinessOffer.objects.filter(variant=self.variant)
        self.assertEqual(offers.count(), 1)
        offer = offers.get()
        self.assertEqual(str(offer.price), "250.00")
        self.assertEqual(offer.cost_strategy.code, "latest")
        self.assertEqual(offer.expected_profit_percentage, Decimal("15.00"))
        self.assertFalse(offer.is_active)

    def test_blank_strategy_fields_leave_the_stored_config_alone(self):
        """The NOT NULL config columns must not be cleared by a blank value."""
        self._patch_pricing({
            "cost_strategy": "fifo_next",
            "expected_profit_percentage": "10",
        })

        request = self.factory.patch(
            f"/vendor/variants/{self.variant.id}",
            {"price": "300.00", "cost_strategy": "", "expected_profit_percentage": ""},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantDetailView.as_view()(
            request, variant_id=self.variant.id
        )

        self.assertEqual(response.status_code, 200, response.data)
        offer = BusinessOffer.objects.get(variant=self.variant)
        self.assertEqual(str(offer.price), "300.00")
        self.assertEqual(offer.cost_strategy.code, "fifo_next")
        self.assertEqual(offer.expected_profit_percentage, Decimal("10.00"))
