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

        cls.business_no_home = BusinessProfile.objects.create(
            business_name="no-home-shop",
            display_name="No Home Shop",
            status=cls.active_status,
        )
        cls.subdomain_no_home = BusinessSubdomain.objects.create(
            business=cls.business_no_home,
            subdomain="no-home-shop",
            status=cls.active_sub_status,
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

    def test_business_without_custom_homepage_returns_404_and_negative_caches(self):
        from core.services import CacheService
        from domains.storefront.cache import page_cache_key

        cache = CacheService()
        cache_key = page_cache_key("home", business_id=self.business_no_home.id)
        cache.delete_public(cache_key)

        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="no-home-shop",
        )
        self.assertEqual(response.status_code, 404)

        # Verify negative cache was set
        cached = cache.get_public(cache_key)
        self.assertIs(cached, False)

        # Subsequent call hits the negative cache
        response2 = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="no-home-shop",
        )
        self.assertEqual(response2.status_code, 404)

    def test_platform_home_when_draft_returns_404(self):
        from domains.storefront.cache import invalidate_page_cache

        self.platform_home.status = ContentPage.Status.DRAFT
        self.platform_home.save()
        invalidate_page_cache("home")

        try:
            response = self.client.get("/api/v1/storefront/home")
            self.assertEqual(response.status_code, 404)
        finally:
            self.platform_home.status = ContentPage.Status.PUBLISHED
            self.platform_home.save()
            invalidate_page_cache("home")

    def test_pages_slug_endpoint_and_legacy_page_endpoint(self):
        response1 = self.client.get("/api/v1/storefront/pages/about")
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response1.data["data"]["title"], "About Us")

        response2 = self.client.get("/api/v1/storefront/page/about")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data["data"]["title"], "About Us")

    def test_pages_slug_business_scoping(self):
        biz_page = BusinessPage.objects.create(
            business=self.business,
            title="Sol Terms",
            slug="terms",
            status=BusinessPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        response = self.client.get(
            f"/api/v1/storefront/pages/{biz_page.slug}",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Sol Terms")

    def test_pages_slug_preview_platform(self):
        response = self.client.get("/api/v1/storefront/pages/draft-page/preview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Draft Page")

    def test_pages_slug_preview_business(self):
        biz_draft = BusinessPage.objects.create(
            business=self.business,
            title="Sol Draft",
            slug="sol-draft",
            status=BusinessPage.Status.DRAFT,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        response = self.client.get(
            f"/api/v1/storefront/pages/{biz_draft.slug}/preview",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Sol Draft")

    def test_pages_preview_rejects_archived_page(self):
        ContentPage.objects.create(
            title="Archived Page",
            slug="archived-page",
            status=ContentPage.Status.ARCHIVED,
            published_content={},
            draft_content={},
        )
        response = self.client.get("/api/v1/storefront/pages/archived-page/preview")
        self.assertEqual(response.status_code, 404)

    def test_landing_page_preview_platform(self):
        from domains.content.models import LandingPage as ContentLandingPage

        landing = ContentLandingPage.objects.create(
            title="Platform Landing",
            slug="platform-landing",
            status=ContentLandingPage.Status.DRAFT,
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        response = self.client.get(f"/api/v1/storefront/landing-pages/{landing.slug}/preview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Platform Landing")

    def test_landing_page_preview_business(self):
        from domains.business_content.models import LandingPage as BusinessLandingPage

        biz_landing = BusinessLandingPage.objects.create(
            business=self.business,
            title="Sol Landing",
            slug="sol-landing",
            status=BusinessLandingPage.Status.DRAFT,
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        response = self.client.get(
            f"/api/v1/storefront/landing-pages/{biz_landing.slug}/preview",
            HTTP_X_TENANT_SUBDOMAIN="sol-shop",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Sol Landing")

    def test_landing_page_preview_rejects_archived(self):
        from domains.content.models import LandingPage as ContentLandingPage

        ContentLandingPage.objects.create(
            title="Archived Landing",
            slug="archived-landing",
            status=ContentLandingPage.Status.ARCHIVED,
            draft_content={},
            published_content={},
        )
        response = self.client.get("/api/v1/storefront/landing-pages/archived-landing/preview")
        self.assertEqual(response.status_code, 404)

    def test_pages_detail_and_preview_contain_seo_field(self):
        from domains.content.models import LandingPage as ContentLandingPage, SEORecord

        seo_page = ContentPage.objects.create(
            title="SEO Test Page",
            slug="seo-test",
            status=ContentPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        SEORecord.objects.create(
            resource_type="page",
            resource_id=seo_page.id,
            title="SEO Page Title",
            description="SEO Page Description",
        )

        # 1. GET /storefront/pages/{slug}
        resp1 = self.client.get(f"/api/v1/storefront/pages/{seo_page.slug}")
        self.assertEqual(resp1.status_code, 200)
        self.assertIn("seo", resp1.data["data"])
        self.assertIsNotNone(resp1.data["data"]["seo"])
        self.assertEqual(resp1.data["data"]["seo"]["title"], "SEO Page Title")
        self.assertEqual(resp1.data["data"]["seo"]["description"], "SEO Page Description")

        # 2. GET /storefront/pages/{slug}/preview
        resp2 = self.client.get(f"/api/v1/storefront/pages/{seo_page.slug}/preview")
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("seo", resp2.data["data"])
        self.assertIsNotNone(resp2.data["data"]["seo"])
        self.assertEqual(resp2.data["data"]["seo"]["title"], "SEO Page Title")

        # 3. GET /storefront/landing-pages/{slug}/preview
        landing = ContentLandingPage.objects.create(
            title="SEO Landing",
            slug="seo-landing",
            status=ContentLandingPage.Status.DRAFT,
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        SEORecord.objects.create(
            resource_type="landing_page",
            resource_id=landing.id,
            title="SEO Landing Title",
            description="SEO Landing Description",
        )
        resp3 = self.client.get(f"/api/v1/storefront/landing-pages/{landing.slug}/preview")
        self.assertEqual(resp3.status_code, 200)
        self.assertIn("seo", resp3.data["data"])
        self.assertIsNotNone(resp3.data["data"]["seo"])
        self.assertEqual(resp3.data["data"]["seo"]["title"], "SEO Landing Title")
