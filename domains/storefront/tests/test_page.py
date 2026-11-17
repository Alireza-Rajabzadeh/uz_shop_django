from rest_framework.test import APITestCase

from domains.business.enums import BusinessStatusEnum, BusinessSubdomainEnum
from domains.business.models import (
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
)
from domains.business_content.models import Page as BusinessPage
from domains.content.models import Page as ContentPage


class StorefrontPageAPITests(APITestCase):
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
            business_name="sol-shop",
            display_name="Sol Shop",
            status=cls.active_status,
        )
        cls.subdomain = BusinessSubdomain.objects.create(
            business=cls.business,
            subdomain="sol-shop",
            status=cls.active_sub_status,
        )

        content_payload = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

        # Platform pages
        cls.platform_home = ContentPage.objects.create(
            title="Platform Home",
            slug="home",
            status=ContentPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
        )
        cls.platform_about = ContentPage.objects.create(
            title="About Us",
            slug="about",
            status=ContentPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
        )
        cls.platform_draft = ContentPage.objects.create(
            title="Draft Page",
            slug="draft-page",
            status=ContentPage.Status.DRAFT,
            published_content=content_payload,
            draft_content=content_payload,
        )

        # Business pages
        cls.business_home = BusinessPage.objects.create(
            business=cls.business,
            title="Sol Home",
            slug="home",
            status=BusinessPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
        )

    def test_published_platform_page_retrieval(self):
        response = self.client.get("/api/v1/storefront/page/about")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "About Us")
        self.assertEqual(response.data["data"]["slug"], "about")

    def test_homepage_retrieval_through_home_slug(self):
        response = self.client.get("/api/v1/storefront/page/home")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Platform Home")

    def test_unpublished_page_returns_404(self):
        response = self.client.get("/api/v1/storefront/page/draft-page")

        self.assertEqual(response.status_code, 404)

    def test_missing_page_returns_404(self):
        response = self.client.get("/api/v1/storefront/page/non-existent-page")

        self.assertEqual(response.status_code, 404)

    def test_business_specific_content_isolation(self):
        response = self.client.get(
            "/api/v1/storefront/page/home",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Sol Home")

    def test_client_provided_business_id_ignored_without_tenant(self):
        response = self.client.get(
            "/api/v1/storefront/page/home?business_id=99999",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Platform Home")

    def test_dedicated_home_endpoint_platform(self):
        response = self.client.get("/api/v1/storefront/home")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Platform Home")

    def test_dedicated_home_endpoint_business_scoping(self):
        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Sol Home")

    def test_dedicated_home_endpoint_ignores_query_param_business_id(self):
        # Client tries to pass business_id=999, but tenant middleware resolves sol-shop
        response = self.client.get(
            "/api/v1/storefront/home?business_id=999",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Sol Home")
