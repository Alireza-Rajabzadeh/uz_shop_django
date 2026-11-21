from rest_framework.test import APITestCase

from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum
from domains.business.models import (
    BusinessCategory,
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
)
from domains.catalog.models import Category, CategoryStatus
from domains.business_content.models import Page as BusinessPage
from domains.content.models import Page as ContentPage


class StorefrontLayoutAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_status, _ = BusinessStatus.objects.get_or_create(
            id=BusinessStatusEnum.ACTIVE.value,
            defaults={"name": "Active", "title": "Active"},
        )
        cls.active_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=BusinessSubdomainEnum.ACTIVE.value,
            defaults={"code": "active", "name": "Active", "title": "Active"},
        )

        cls.business = BusinessProfile.objects.create(
            business_name="apex-shop",
            display_name="Apex Shop",
            status=cls.active_status,
        )
        cls.subdomain = BusinessSubdomain.objects.create(
            business=cls.business,
            subdomain="apex-shop",
            status=cls.active_sub_status,
        )

        cls.cat_status, _ = CategoryStatus.objects.get_or_create(
            name="Active", defaults={"name": "Active"}
        )
        cls.cat1 = Category.objects.create(
            name="Electronics",
            slug="electronics",
            status=cls.cat_status,
        )
        cls.cat2 = Category.objects.create(
            name="Clothing",
            slug="clothing",
            status=cls.cat_status,
        )

        # Business only registers for cat1 (Electronics)
        BusinessCategory.objects.create(
            business=cls.business,
            category=cls.cat1,
        )

    def test_platform_layout_resolution(self):
        response = self.client.get("/api/v1/storefront/layout")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        data = response.data["data"]

        self.assertTrue(data["config"]["is_platform"])
        self.assertIsNone(data["config"]["tenant"])
        # Both categories present in platform layout
        cat_ids = [c["id"] for c in data["categories"]]
        self.assertIn(self.cat1.id, cat_ids)
        self.assertIn(self.cat2.id, cat_ids)

    def test_valid_business_layout_resolution(self):
        response = self.client.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="apex-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        data = response.data["data"]

        self.assertFalse(data["config"]["is_platform"])
        self.assertEqual(data["config"]["tenant"]["id"], self.business.id)
        # Only cat1 registered for this business
        cat_ids = [c["id"] for c in data["categories"]]
        self.assertIn(self.cat1.id, cat_ids)
        self.assertNotIn(self.cat2.id, cat_ids)

    def test_unresolved_business_serves_platform_layout(self):
        response = self.client.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="non-existent-subdomain",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["config"]["is_platform"])

    def test_empty_layout_sections_are_valid(self):
        # Platform has no footer by default, empty theme and header
        response = self.client.get("/api/v1/storefront/layout")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["theme"], {})
        self.assertEqual(data["header"], {})
        self.assertIsNone(data["footer"])

    def test_platform_footer_resolution(self):
        content_payload = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }
        page = ContentPage.objects.create(
            title="Platform Footer",
            slug="footer",
            status=ContentPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
        )

        response = self.client.get("/api/v1/storefront/layout")
        self.assertEqual(response.status_code, 200)
        footer = response.data["data"]["footer"]
        self.assertIsNotNone(footer)
        self.assertEqual(footer["slug"], "footer")

        page.status = ContentPage.Status.DRAFT
        page.save()

        response = self.client.get("/api/v1/storefront/layout")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["data"]["footer"])

    def test_business_footer_resolution(self):
        content_payload = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }
        BusinessPage.objects.create(
            business=self.business,
            title="Business Footer",
            slug="footer",
            status=BusinessPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
        )

        response = self.client.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="apex-shop",
        )
        self.assertEqual(response.status_code, 200)
        footer = response.data["data"]["footer"]
        self.assertIsNotNone(footer)
        self.assertEqual(footer["slug"], "footer")
