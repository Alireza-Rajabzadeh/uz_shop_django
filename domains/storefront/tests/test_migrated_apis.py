from django.test import TestCase
from rest_framework.test import APIClient

from domains.catalog.models import (
    Brand,
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
)


class MigratedStorefrontAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category_status = CategoryStatus.objects.create(name="active")
        self.product_status = ProductStatus.objects.create(name="active")

        self.category = Category.objects.create(
            name="Smartphones",
            slug="smartphones",
            status=self.category_status,
        )
        self.brand = Brand.objects.create(name="PixelBrand")
        self.product = Product.objects.create(
            name="Pixel 9 Pro",
            slug="pixel-9-pro",
            brand=self.brand,
            status=self.product_status,
        )
        self.product.categories.add(self.category)

    def test_new_storefront_product_listing(self):
        response = self.client.get("/api/v1/storefront/products")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIn("results", response.data["data"])
        self.assertIn("facets", response.data["data"])

    def test_new_storefront_product_detail(self):
        response = self.client.get(f"/api/v1/storefront/products/{self.product.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["name"], "Pixel 9 Pro")

    def test_new_storefront_product_quick_view(self):
        response = self.client.get(
            f"/api/v1/storefront/products/{self.product.slug}/quick-view"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["name"], "Pixel 9 Pro")
