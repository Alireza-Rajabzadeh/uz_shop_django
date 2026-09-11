from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
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
from domains.marketplace.models import BusinessOffer
from domains.vendor.models import Vendor, VendorStatus


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
        self.business = BusinessProfile.objects.create(
            id=1,
            vendor=self.vendor,
            business_name="Test Business",
            display_name="Test Business",
        )
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
        from django.db import IntegrityError

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
        from domains.catalog.services.variant_service import VariantService
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
        from domains.catalog.services.variant_service import VariantService
        effective = VariantService().calculate_discounted_price(self.variant, offer)
        self.assertEqual(effective, Decimal("75.00"))

    def test_no_discount_returns_full_price(self):
        offer = BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price=Decimal("100.00"),
        )
        from domains.catalog.services.variant_service import VariantService
        effective = VariantService().calculate_discounted_price(self.variant, offer)
        self.assertEqual(effective, Decimal("100.00"))


class BusinessOfferAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="marketplace-admin", password="password"
        )
        self.client.force_authenticate(self.user)

        vendor_status = VendorStatus.objects.create(name="active", title="Active")
        self.vendor = Vendor.objects.create(
            phone="+9990000003",
            first_name="API",
            last_name="Vendor",
            national_id="0000000003",
            vendor_code="V003",
            status=vendor_status,
        )
        self.business = BusinessProfile.objects.create(
            id=1,
            vendor=self.vendor,
            business_name="API Business",
            display_name="API Business",
        )
        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Phones", status=category_status)
        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="API Product", status=product_status)
        self.product.categories.add(self.category)
        self.variant = ProductVariants.objects.create(
            product=self.product,
            sku="API-SKU-001",
            combination_key="BLK-128GB",
        )

    def test_create_offer(self):
        response = self.client.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["business"], self.business.id)
        self.assertEqual(response.data["data"]["variant"], self.variant.id)
        self.assertEqual(Decimal(response.data["data"]["price"]), Decimal("100.00"))

    def test_create_offer_with_discount(self):
        response = self.client.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
                "discount_type": "percentage",
                "discount_value": "10.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["discount_type"], "percentage")

    def test_list_offers(self):
        BusinessOffer.objects.create(
            business=self.business, variant=self.variant, price=Decimal("50.00")
        )
        response = self.client.get("/api/marketplace/offers")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_get_offer_detail(self):
        offer = BusinessOffer.objects.create(
            business=self.business, variant=self.variant, price=Decimal("75.00")
        )
        response = self.client.get(f"/api/marketplace/offers/{offer.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], offer.id)
        self.assertEqual(Decimal(response.data["data"]["price"]), Decimal("75.00"))

    def test_patch_offer_price(self):
        offer = BusinessOffer.objects.create(
            business=self.business, variant=self.variant, price=Decimal("100.00")
        )
        response = self.client.patch(
            f"/api/marketplace/offers/{offer.id}",
            {"price": "89.99"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.price, Decimal("89.99"))

    def test_delete_offer(self):
        offer = BusinessOffer.objects.create(
            business=self.business, variant=self.variant, price=Decimal("50.00")
        )
        response = self.client.delete(f"/api/marketplace/offers/{offer.id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BusinessOffer.objects.filter(pk=offer.id).exists())

    def test_duplicate_offer_returns_400(self):
        BusinessOffer.objects.create(
            business=self.business, variant=self.variant, price=Decimal("50.00")
        )
        response = self.client.post(
            "/api/marketplace/offers",
            {"business": self.business.id, "variant": self.variant.id, "price": "60.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_percentage_discount_cannot_exceed_100(self):
        response = self.client.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
                "discount_type": "percentage",
                "discount_value": "150.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_fixed_discount_cannot_exceed_price(self):
        response = self.client.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
                "discount_type": "fixed",
                "discount_value": "200.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_discount_type_requires_value(self):
        response = self.client.post(
            "/api/marketplace/offers",
            {
                "business": self.business.id,
                "variant": self.variant.id,
                "price": "100.00",
                "discount_type": "percentage",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
