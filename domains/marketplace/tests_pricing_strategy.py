from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
)
from domains.content.contracts import load_content_contracts
from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
from domains.inventory.services.inventory_pricing_service import InventoryPricingService
from domains.marketplace.models import BusinessOffer, OfferPriceHistory, PricingStrategy
from domains.marketplace.services import MarketplacePricingService
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.inventory import VendorPricingStrategiesView


def _guide_contract_map():
    return {
        component["key"]: component
        for component in load_content_contracts()["components"]
    }


def _ensure_business(vendor, name):
    """BusinessProfile is a singleton (id=1) pre-created by a data migration."""
    business, _ = BusinessProfile.objects.get_or_create(
        id=1,
        defaults={"business_name": name, "display_name": name},
    )
    business.vendor = vendor
    business.business_name = name
    business.display_name = name
    business.save()
    return business


class PricingStrategyReferenceDataTests(TestCase):
    """The table is display data; the enum stays the code vocabulary.

    Both were seeded from the same enum, so the useful failure mode here is
    a later edit that lets them drift apart.
    """

    def test_table_codes_match_the_enum(self):
        self.assertEqual(
            set(PricingStrategy.objects.values_list("code", flat=True)),
            InventoryPricingService.strategy_codes(),
        )

    def test_seed_ids_are_stable_and_latest_is_first(self):
        self.assertEqual(
            list(PricingStrategy.objects.order_by("id").values_list("id", "code")),
            [
                (1, VariantCostStrategyEnum.LATEST.value),
                (2, VariantCostStrategyEnum.WEIGHTED_AVERAGE.value),
                (3, VariantCostStrategyEnum.FIFO_NEXT.value),
            ],
        )
        # BusinessOffer.cost_strategy defaults to id=1.
        self.assertEqual(
            PricingStrategy.objects.get(id=1).code,
            VariantCostStrategyEnum.LATEST.value,
        )

    def test_every_strategy_carries_labels_and_a_guide(self):
        contracts = _guide_contract_map()
        seen_ids = set()
        for strategy in PricingStrategy.objects.all():
            with self.subTest(code=strategy.code):
                self.assertTrue(strategy.name.strip())
                self.assertTrue(strategy.fa_name.strip())
                components = strategy.description.get("components")
                self.assertIsInstance(components, list)
                self.assertTrue(components, "guide must contain components")
                for component in components:
                    self.assertIn("id", component)
                    self.assertNotIn(component["id"], seen_ids, "component ids are unique")
                    seen_ids.add(component["id"])
                    contract = contracts.get(component["key"])
                    self.assertIsNotNone(
                        contract, f"{component['key']} is not a registered content component"
                    )
                    self.assertEqual(contract["version"], component["version"])
                    for prop_name, prop in contract["props"].items():
                        if prop.get("required"):
                            self.assertIn(prop_name, component["props"])
                        self.assertIsInstance(
                            component["props"].get(prop_name), str
                        )

class PricingStrategyServiceTests(TestCase):
    def setUp(self):
        vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09351112233",
            password="pass1234",
            first_name="Strategy",
            last_name="Vendor",
            national_id="5566778899",
            status=vendor_status,
        )
        self.business = _ensure_business(self.vendor, "Strategy Business")
        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Strategy Phones", status=category_status)
        BusinessCategory.objects.create(business=self.business, category=self.category)
        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Strategy Product", status=product_status)
        self.variant_status = ProductVariantStatus.objects.create(name="active")
        self.variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_status,
            sku="STRATEGY-SKU",
            combination_key="BLK-256GB",
        )

    def test_get_strategies_exposes_guide_payload(self):
        rows = InventoryPricingService().get_strategies()
        self.assertEqual(
            {row["code"] for row in rows}, InventoryPricingService.strategy_codes()
        )
        for row in rows:
            self.assertIn("fa_name", row)
            self.assertIn("description", row)
            self.assertTrue(row["fa_name"])
            self.assertTrue(row["description"]["components"])

    def test_create_offer_resolves_code_string_to_the_row(self):
        offer = MarketplacePricingService.create_offer(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
            cost_strategy=VariantCostStrategyEnum.FIFO_NEXT.value,
        )
        self.assertIsInstance(offer.cost_strategy, PricingStrategy)
        self.assertEqual(offer.cost_strategy.code, "fifo_next")
        offer.refresh_from_db()
        self.assertEqual(offer.cost_strategy.code, "fifo_next")
        # The audit row keeps a plain code snapshot, not a foreign key.
        history = OfferPriceHistory.objects.get(offer=offer)
        self.assertEqual(history.cost_strategy, "fifo_next")

    def test_create_offer_defaults_to_latest(self):
        offer = MarketplacePricingService.create_offer(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
        )
        self.assertEqual(offer.cost_strategy.code, "latest")

    def test_create_offer_rejects_unknown_code(self):
        with self.assertRaises(MarketplacePricingService.ValidationError):
            MarketplacePricingService.create_offer(
                business=self.business,
                variant=self.variant,
                cost_strategy="not-a-strategy",
            )
        self.assertFalse(BusinessOffer.objects.exists())

    def test_update_offer_resolves_code_string(self):
        offer = MarketplacePricingService.create_offer(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
        )
        offer = MarketplacePricingService.update_offer(
            offer, cost_strategy=VariantCostStrategyEnum.WEIGHTED_AVERAGE.value
        )
        self.assertEqual(offer.cost_strategy.code, "weighted_average")

    def test_strategy_filter_uses_the_code_column(self):
        MarketplacePricingService.create_offer(
            business=self.business,
            variant=self.variant,
            cost_strategy=VariantCostStrategyEnum.FIFO_NEXT.value,
        )
        self.assertEqual(
            list(
                InventoryPricingService().search_pricing(strategy="fifo_next").values_list(
                    "pk", flat=True
                )
            ),
            [self.variant.pk],
        )
        self.assertEqual(
            list(
                InventoryPricingService().search_pricing(strategy="latest").values_list(
                    "pk", flat=True
                )
            ),
            [],
        )


class PricingStrategyApiTests(APITestCase):
    """`/api/marketplace/offers` must keep speaking code strings.

    The field became a ForeignKey, which a plain ModelSerializer would expose
    as a row id in both directions.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = Vendor.objects.create_user(
            phone="09354445566",
            password="pass1234",
            first_name="Offer",
            last_name="Admin",
            national_id="1112223344",
            status=VendorStatus.objects.create(
                id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
            ),
        )
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.business = _ensure_business(self.user, "Offer Business")
        category_status = CategoryStatus.objects.create(name="active")
        category = Category.objects.create(name="Offer Phones", status=category_status)
        BusinessCategory.objects.create(business=self.business, category=category)
        product_status = ProductStatus.objects.create(name="active")
        product = Product.objects.create(name="Offer Product", status=product_status)
        self.variant = ProductVariants.objects.create(
            product=product,
            status=ProductVariantStatus.objects.create(name="active"),
            sku="OFFER-SKU",
            combination_key="WHT-128GB",
        )

    def test_create_and_read_offer_expose_the_code_not_the_id(self):
        from domains.marketplace.api.views import BusinessOfferListCreate

        request = self.factory.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
                "cost_strategy": "fifo_next",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = BusinessOfferListCreate.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["cost_strategy"], "fifo_next")

        offer = BusinessOffer.objects.get(pk=response.data["data"]["id"])
        self.assertEqual(offer.cost_strategy.code, "fifo_next")

    def test_create_offer_with_unknown_code_is_rejected(self):
        from domains.marketplace.api.views import BusinessOfferListCreate

        request = self.factory.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "cost_strategy": "not-a-strategy",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = BusinessOfferListCreate.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BusinessOffer.objects.exists())

    def test_vendor_pricing_strategies_endpoint_returns_guides(self):
        request = self.factory.get("/vendor/pricing-strategies")
        force_authenticate(request, user=self.user)
        response = VendorPricingStrategiesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertIn("fa_name", row)
            self.assertIn("description", row)
            self.assertTrue(row["description"]["components"])
