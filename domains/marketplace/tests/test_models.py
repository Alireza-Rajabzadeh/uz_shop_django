from decimal import Decimal

from django.db import IntegrityError, models
from rest_framework.test import APITestCase

from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    ProductVariantStatus,
)
from domains.catalog.services.variant_service import VariantService
from domains.marketplace.models import BusinessOffer
from domains.vendor.models import Vendor, VendorStatus


def _ensure_business(vendor, name):
    """BusinessProfile is a singleton (id=1) and is pre-created by the
    inventory data migration, so reuse it instead of inserting a duplicate."""
    business, _ = BusinessProfile.objects.get_or_create(
        id=1,
        defaults={"business_name": name, "display_name": name},
    )
    business.vendor = vendor
    business.business_name = name
    business.display_name = name
    business.save()
    return business


class BusinessOfferModelTests(APITestCase):
    def setUp(self):
        vendor_status = VendorStatus.objects.create(name="active", title="Active")
        self.vendor = Vendor.objects.create(
            phone="+9990000001",
            first_name="Test",
            last_name="Vendor",
            national_id="0000000001",
            vendor_code="V001",
            status=vendor_status,
        )
        self.business = _ensure_business(self.vendor, "Test Business")
        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Phones", status=category_status)
        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Test Product", status=product_status)
        self.product.categories.add(self.category)
        self.variant_status = ProductVariantStatus.objects.create(name="active")
        self.variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_status,
            sku="TEST-SKU-001",
            combination_key="BLK-128GB",
        )

    def test_business_can_create_offer_for_variant(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
        )
        self.assertEqual(offer.business, self.business)
        self.assertEqual(offer.variant, self.variant)
        self.assertEqual(offer.price, Decimal("100.00"))
        self.assertTrue(offer.is_active)

    def test_unique_constraint_allows_same_variant_with_different_business(self):
        BusinessOffer.objects.create(business=self.business, variant=self.variant)
        constraint_names = [
            c.name
            for c in BusinessOffer._meta.constraints
            if isinstance(c, models.UniqueConstraint)
        ]
        self.assertIn("marketplace_offer_business_variant_unique", constraint_names)

    def test_one_business_cannot_create_duplicate_offer_for_same_variant(self):
        BusinessOffer.objects.create(business=self.business, variant=self.variant)
        with self.assertRaises(IntegrityError):
            BusinessOffer.objects.create(business=self.business, variant=self.variant)

    def test_is_active_defaults_to_true(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
        )
        self.assertTrue(offer.is_active)

    def test_offer_does_not_contain_inventory_fields(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
        )
        self.assertFalse(hasattr(offer, "quantity"))
        self.assertFalse(hasattr(offer, "stock"))
        self.assertFalse(hasattr(offer, "reserved"))
        self.assertFalse(hasattr(offer, "warehouse"))

    def test_offer_has_pricing_fields(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("99.99"),
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )
        self.assertEqual(offer.price, Decimal("99.99"))
        self.assertEqual(offer.discount_type, "percentage")
        self.assertEqual(offer.discount_value, Decimal("10.00"))

    def test_product_variant_sku_unchanged(self):
        original_sku = self.variant.sku
        BusinessOffer.objects.create(business=self.business, variant=self.variant)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.sku, original_sku)

    def test_discounted_price_calculation(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )
        effective = VariantService().calculate_discounted_price(self.variant, offer)
        self.assertEqual(effective, Decimal("90.00"))

    def test_fixed_discount_calculation(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
            discount_type="fixed",
            discount_value=Decimal("25.00"),
        )
        effective = VariantService().calculate_discounted_price(self.variant, offer)
        self.assertEqual(effective, Decimal("75.00"))

    def test_no_discount_returns_full_price(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
        )
        effective = VariantService().calculate_discounted_price(self.variant, offer)
        self.assertEqual(effective, Decimal("100.00"))
