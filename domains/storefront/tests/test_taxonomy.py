from urllib.parse import quote

from rest_framework.test import APITestCase

from domains.catalog.models import Brand, Category, CategoryStatus
from domains.content.models import SEORecord


class StorefrontTaxonomyTests(APITestCase):
    def setUp(self):
        self.active = CategoryStatus.objects.create(name="active")
        self.inactive = CategoryStatus.objects.create(name="inactive")

    def get_resource(self, resource_type, slug):
        return self.client.get(
            f"/api/v1/storefront/taxonomy/{resource_type}/{quote(slug, safe='')}"
        )

    def test_category_returns_identity_and_seo(self):
        category = Category.objects.create(name="Mobile Phones", status=self.active)
        SEORecord.objects.create(
            resource_type="category", resource_id=category.id, title="Shop phones"
        )

        response = self.get_resource("category", category.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["resource"], {
            "id": category.id, "slug": category.slug, "name": category.name,
        })
        self.assertEqual(response.data["data"]["seo"]["title"], "Shop phones")

    def test_category_without_seo_returns_null_seo(self):
        category = Category.objects.create(name="Laptops", status=self.active)

        response = self.get_resource("category", category.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["resource"]["id"], category.id)
        self.assertIsNone(response.data["data"]["seo"])

    def test_brand_returns_identity_and_seo(self):
        brand = Brand.objects.create(name="Acme")
        SEORecord.objects.create(
            resource_type="brand", resource_id=brand.id, title="Acme Official"
        )

        response = self.get_resource("brand", brand.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["resource"], {
            "id": brand.id, "slug": brand.slug, "name": brand.name,
        })
        self.assertEqual(response.data["data"]["seo"]["title"], "Acme Official")

    def test_brand_without_seo_returns_null_seo(self):
        brand = Brand.objects.create(name="BrandX")

        response = self.get_resource("brand", brand.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["resource"]["id"], brand.id)
        self.assertIsNone(response.data["data"]["seo"])

    def test_inactive_category_returns_404(self):
        category = Category.objects.create(name="Old Phones", status=self.inactive)
        self.assertEqual(self.get_resource("category", category.slug).status_code, 404)

    def test_inactive_ancestor_returns_404(self):
        parent = Category.objects.create(name="Hidden parent", status=self.inactive)
        child = Category.objects.create(name="Visible child", status=self.active, parent=parent)
        self.assertEqual(self.get_resource("category", child.slug).status_code, 404)

    def test_nonexistent_resource_returns_404(self):
        response = self.get_resource("category", "does-not-exist")
        self.assertEqual(response.status_code, 404)

        response = self.get_resource("brand", "does-not-exist")
        self.assertEqual(response.status_code, 404)

        response = self.get_resource("unknown_type", "whatever")
        self.assertEqual(response.status_code, 404)

    def test_unicode_slug_is_supported(self):
        category = Category.objects.create(name="گوشی موبایل", status=self.active)

        response = self.get_resource("category", category.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["resource"]["slug"], category.slug)
