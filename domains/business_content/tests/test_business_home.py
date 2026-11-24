from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.services import CacheService
from domains.business.models import (
    BusinessProfile,
    BusinessStatus,
    BusinessSubdomain,
    BusinessSubdomainStatus,
)
from domains.packages.models import Feature, Package, PackageFeature
from domains.packages.enums import PackageFeatureEnum

from domains.storefront.cache import page_cache_key, invalidate_page_cache
from ..cache import invalidate_page
from ..models import Page
from ..services.page_service import PageService


class BusinessHomePageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cache = CacheService()

        # Statuses
        self.active_biz_status, _ = BusinessStatus.objects.get_or_create(
            id=1, defaults={"code": "active", "name": "Active", "title": "Active"}
        )
        self.active_sub_status, _ = BusinessSubdomainStatus.objects.get_or_create(
            id=1, defaults={"code": "active", "name": "Active", "title": "Active"}
        )

        # Provision packages & features
        self.feature_landing, _ = Feature.objects.get_or_create(
            code=PackageFeatureEnum.CONTENT_LANDINGPAGE.code,
            defaults={"name": "Landing pages", "description": "Landing page feature"},
        )
        self.pro_package, _ = Package.objects.get_or_create(
            code="pro",
            defaults={"name": "Pro", "price": "1000", "is_active": True},
        )
        PackageFeature.objects.get_or_create(
            package=self.pro_package,
            feature=self.feature_landing,
            defaults={"config": {"enabled": True}},
        )

        self.free_package, _ = Package.objects.get_or_create(
            code="free",
            defaults={"name": "Free", "price": "0", "is_active": True},
        )

        # Business A: Pro package, active subdomain "alpha"
        self.business_alpha = BusinessProfile.objects.create(
            id=101,
            business_name="alpha",
            display_name="Alpha Store",
            status=self.active_biz_status,
            package=self.pro_package,
        )
        self.subdomain_alpha = BusinessSubdomain.objects.create(
            business=self.business_alpha,
            subdomain="alpha",
            status=self.active_sub_status,
        )

        # Business B: Free package, active subdomain "beta"
        self.business_beta = BusinessProfile.objects.create(
            id=102,
            business_name="beta",
            display_name="Beta Store",
            status=self.active_biz_status,
            package=self.free_package,
        )
        self.subdomain_beta = BusinessSubdomain.objects.create(
            business=self.business_beta,
            subdomain="beta",
            status=self.active_sub_status,
        )

        self.valid_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

        # Clear relevant cache keys
        invalidate_page_cache("home", self.business_alpha.id)
        invalidate_page_cache("home", self.business_beta.id)

    def tearDown(self):
        invalidate_page_cache("home", self.business_alpha.id)
        invalidate_page_cache("home", self.business_beta.id)

    def test_cached_homepage_content_returned_without_db_queries(self):
        """Cached homepage content is returned without additional database queries."""
        cache_key = page_cache_key("home", business_id=self.business_alpha.id)
        cached_payload = {
            "id": 999,
            "title": "Cached Storefront Home",
            "slug": "home",
            "status": "published",
            "content": {"components": []},
            "seo": None,
        }
        self.cache.put_public(cache_key, cached_payload, ttl=300)

        # Query with business subdomain
        with patch.object(Page.objects, "filter") as mock_page_filter:
            response = self.client.get(
                "/api/v1/storefront/home",
                HTTP_X_TENANT_SUBDOMAIN="alpha",
            )
            mock_page_filter.assert_not_called()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Cached Storefront Home")

    def test_cached_negative_result_returned_without_db_queries(self):
        """Cached negative result returns 404 without additional database queries."""
        cache_key = page_cache_key("home", business_id=self.business_alpha.id)
        # Put negative cached result (False)
        self.cache.put_public(cache_key, False, ttl=60)

        with patch.object(Page.objects, "filter") as mock_page_filter:
            response = self.client.get(
                "/api/v1/storefront/home",
                HTTP_X_TENANT_SUBDOMAIN="alpha",
            )
            mock_page_filter.assert_not_called()

        self.assertEqual(response.status_code, 404)

    def test_cache_miss_triggers_eligibility_and_publication_checks(self):
        """Cache miss triggers eligibility and publication checks."""
        Page.objects.create(
            business=self.business_alpha,
            title="Alpha Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content=self.valid_content,
        )

        service = PageService()
        with patch.object(
            PageService, "allows_custom_homepage", wraps=service.allows_custom_homepage
        ) as mock_eligibility, patch.object(
            PageService, "get_published_home_page", wraps=service.get_published_home_page
        ) as mock_published:
            response = self.client.get(
                "/api/v1/storefront/home",
                HTTP_X_TENANT_SUBDOMAIN="alpha",
            )

            self.assertEqual(response.status_code, 200)
            mock_eligibility.assert_called_once()
            mock_published.assert_called_once()

    def test_valid_published_content_resolved_cached_and_returned(self):
        """Valid published content is resolved, cached, and returned."""
        Page.objects.create(
            business=self.business_alpha,
            title="Alpha Storefront Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content=self.valid_content,
            cache_ttl=120,
        )

        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Alpha Storefront Home")
        self.assertEqual(response.data["data"]["slug"], "home")

        # Verify it was cached in Redis under business-content:home:{business_id}
        cache_key = page_cache_key("home", business_id=self.business_alpha.id)
        cached = self.cache.get_public(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["title"], "Alpha Storefront Home")

    def test_business_without_package_permission_receives_404(self):
        """Business on an inactive package receives 404."""
        self.free_package.is_active = False
        self.free_package.save()
        try:
            Page.objects.create(
                business=self.business_beta,
                title="Beta Home",
                slug=PageService.HOME_SLUG,
                status=Page.Status.PUBLISHED,
                published_content=self.valid_content,
            )

            response = self.client.get(
                "/api/v1/storefront/home",
                HTTP_X_TENANT_SUBDOMAIN="beta",
            )

            self.assertEqual(response.status_code, 404)

            # Verify negative result was cached
            cache_key = page_cache_key("home", business_id=self.business_beta.id)
            cached = self.cache.get_public(cache_key)
            self.assertIs(cached, False)
        finally:
            self.free_package.is_active = True
            self.free_package.save()

    def test_business_without_published_content_receives_404(self):
        """Business without any published home page receives 404."""
        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )

        self.assertEqual(response.status_code, 404)

        # Verify negative result was cached
        cache_key = page_cache_key("home", business_id=self.business_alpha.id)
        cached = self.cache.get_public(cache_key)
        self.assertIs(cached, False)

    def test_invalid_or_unavailable_content_receives_404(self):
        """Invalid content structure receives 404."""
        Page.objects.create(
            business=self.business_alpha,
            title="Malformed Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content="invalid-string-content",
        )

        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )

        self.assertEqual(response.status_code, 404)

        # Malformed components
        invalidate_page_cache("home", self.business_alpha.id)
        Page.objects.filter(business=self.business_alpha).update(
            published_content={"components": "not-a-list"}
        )

        response2 = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )

        self.assertEqual(response2.status_code, 404)

    def test_draft_content_is_never_exposed(self):
        """Draft content is never exposed through the public endpoint."""
        # 1. Page with status=DRAFT receives 404
        Page.objects.create(
            business=self.business_alpha,
            title="Draft Only Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.DRAFT,
            draft_content={"components": [{"id": "secret-draft-component"}]},
            published_content={},
        )

        response = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )
        self.assertEqual(response.status_code, 404)

        # 2. Page with status=PUBLISHED only returns published_content, never draft_content
        invalidate_page_cache("home", self.business_alpha.id)
        Page.objects.filter(business=self.business_alpha).update(
            status=Page.Status.PUBLISHED,
            draft_content={"components": [{"id": "unreleased-draft"}]},
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
        )

        response2 = self.client.get(
            "/api/v1/storefront/home",
            HTTP_X_TENANT_SUBDOMAIN="alpha",
        )
        self.assertEqual(response2.status_code, 200)
        self.assertNotIn("draft_content", response2.data["data"])
        self.assertEqual(response2.data["data"]["content"]["components"], [])

    def test_unexpected_errors_are_not_converted_into_404_responses(self):
        """Unexpected internal exceptions bubble up and return 500, not 404."""
        Page.objects.create(
            business=self.business_alpha,
            title="Alpha Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content=self.valid_content,
        )

        with patch(
            "domains.business_content.services.page_service.LandingPageContentResolver.resolve",
            side_effect=RuntimeError("Unexpected database disconnect"),
        ):
            response = self.client.get(
                "/api/v1/storefront/home",
                HTTP_X_TENANT_SUBDOMAIN="alpha",
            )

            # Must NOT be 404
            self.assertEqual(response.status_code, 500)
            self.assertFalse(response.data["success"])
