from django.utils import translation
from rest_framework.test import APITestCase

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
)
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus


class VendorInventoryMessageTranslationAPITests(APITestCase):
    """Vendor-facing inventory validation errors must be localized."""

    def setUp(self):
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor = Vendor.objects.create_user(
            phone="09121234567",
            password="pass1234",
            first_name="Message",
            last_name="Vendor",
            national_id="1357924680",
            status=self.vendor_status,
        )
        self.business = BusinessProfile.objects.create(
            id=301,
            vendor=self.vendor,
            business_name="Message Vendor Business",
            display_name="Message Vendor",
        )
        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Message Category",
            status=self.category_status,
        )
        BusinessCategory.objects.create(
            business=self.business,
            category=self.category,
        )
        self.product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(
            name="Message Product",
            status=self.product_status,
        )
        self.product.categories.add(self.category)
        self.variant = ProductVariants.objects.create(
            product=self.product,
            sku="MESSAGE-STOCK-SKU",
            combination_key="message-stock-sku",
        )
        self.client.force_authenticate(self.vendor)

    def _patch_variant(self, payload):
        return self.client.patch(
            f"/api/vendor/variants/{self.variant.id}",
            data=payload,
            format="json",
        )

    def test_sellable_over_quantity_returns_persian_message(self):
        with translation.override("fa"):
            response = self._patch_variant(
                {
                    "inventory_strategy_code": "normal",
                    "inventory": {"quantity": 10, "sellable": 20, "min_stock": 0},
                }
            )

        self.assertEqual(response.status_code, 400, response.data)
        messages = response.data["errors"]["inventory"]["non_field_errors"]
        self.assertIn(
            "تعداد قابل فروش نمی‌تواند بیشتر از موجودی فیزیکی باشد.",
            [str(item) for item in messages],
        )

    def test_sellable_over_quantity_returns_english_for_english_locale(self):
        response = self.client.patch(
            f"/api/vendor/variants/{self.variant.id}",
            data={
                "inventory_strategy_code": "normal",
                "inventory": {"quantity": 10, "sellable": 20, "min_stock": 0},
            },
            format="json",
            HTTP_X_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, 400, response.data)
        messages = response.data["errors"]["inventory"]["non_field_errors"]
        self.assertIn(
            "Sellable quantity cannot exceed physical quantity.",
            [str(item) for item in messages],
        )
