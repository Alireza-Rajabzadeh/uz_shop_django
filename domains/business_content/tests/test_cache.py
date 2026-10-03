from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from domains.business.models import BusinessProfile

from ..models import LandingPage, Page, SEORecord
from ..services import public_business_id
from .factories import storefront_business


class PublicContentCacheTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.business = storefront_business()
        self.content = {"schema_version": 1, "contract_version": 4, "components": []}

    @patch("domains.business_content.views.CacheService")
    @patch("domains.business_content.views.LandingPageContentResolver")
    def test_landing_page_cache_hit_skips_database_and_resolution(self, resolver, cache):
        payload = {"id": 9, "slug": "cached", "content": {"components": []}}
        cache.return_value.get_public.return_value = payload

        response = self.client.get("/api/business-content/landing-pages/cached")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], payload)
        resolver.assert_not_called()

    @patch("domains.business_content.views.CacheService")
    def test_page_cache_miss_writes_final_payload_with_model_ttl(self, cache):
        cache.return_value.get_public.return_value = None
        page = Page.objects.create(
            title="About",
            slug="about",
            business=self.business,
            status=Page.Status.PUBLISHED,
            published_content=self.content,
            cache_ttl=45,
        )

        response = self.client.get(f"/api/business-content/pages/{page.slug}")

        self.assertEqual(response.status_code, 200)
        cache.return_value.put_public.assert_called_once_with(
            "business-content:pages:about", response.data["data"], ttl=45
        )

    @patch("domains.business_content.views.CacheService")
    def test_zero_ttl_disables_home_cache_write(self, cache):
        cache.return_value.get_public.return_value = None
        Page.objects.create(
            title="Home",
            slug="home",
            business=self.business,
            status=Page.Status.PUBLISHED,
            published_content=self.content,
            cache_ttl=0,
        )

        response = self.client.get("/api/business-content/home")

        self.assertEqual(response.status_code, 200)
        cache.return_value.put_public.assert_not_called()

    @patch("domains.business_content.views.CacheService")
    def test_delivery_reads_the_storefront_business(self, cache):
        cache.return_value.get_public.return_value = None
        Page.objects.create(
            title="Other business home",
            slug="home",
            # Explicit pk: `inventory.0022` inserts id=1 directly, so the
            # sequence is behind and a plain create() would collide with it.
            business=BusinessProfile.objects.create(
                id=9988,
                business_name="Other",
                display_name="Other",
            ),
            status=Page.Status.PUBLISHED,
            published_content=self.content,
            cache_ttl=0,
        )

        response = self.client.get("/api/business-content/home")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            public_business_id(),
            BusinessProfile.objects.order_by("id").first().id,
        )


class ContentCacheInvalidationTests(TestCase):
    def setUp(self):
        self.business = storefront_business()

    @patch("domains.business_content.cache.CacheService")
    def test_direct_page_slug_update_invalidates_old_new_and_home_keys(self, cache):
        with self.captureOnCommitCallbacks(execute=True):
            page = Page.objects.create(title="Home", slug="home", business=self.business)
        cache.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            page.slug = "start"
            page.save()

        deleted = {call.args[0] for call in cache.return_value.delete_public.call_args_list}
        self.assertEqual(
            deleted,
            {
                "business-content:pages:home",
                "business-content:home",
                "business-content:pages:start",
            },
        )

    @patch("domains.business_content.cache.CacheService")
    def test_direct_seo_change_invalidates_public_landing_page(self, cache):
        with self.captureOnCommitCallbacks(execute=True):
            page = LandingPage.objects.create(
                title="Sale", slug="sale", business=self.business
            )
        cache.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            SEORecord.objects.create(
                resource_type="landing_page", resource_id=page.id, title="Sale SEO"
            )

        cache.return_value.delete_public.assert_any_call(
            "business-content:landing-pages:sale"
        )
