from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import LandingPage, Page, SEORecord


class PublicContentCacheTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.content = {"schema_version": 1, "contract_version": 3, "components": []}

    @patch("domains.content.views.CacheService")
    @patch("domains.content.views.LandingPageContentResolver")
    def test_landing_page_cache_hit_skips_database_and_resolution(self, resolver, cache):
        payload = {"id": 9, "slug": "cached", "content": {"components": []}}
        cache.return_value.get_public.return_value = payload

        response = self.client.get("/api/content/landing-pages/cached")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], payload)
        resolver.assert_not_called()

    @patch("domains.content.views.CacheService")
    def test_page_cache_miss_hands_the_model_ttl_to_the_cache(self, cache):
        cache.return_value.get_public.return_value = None
        cache.return_value.get_or_set_public.side_effect = lambda key, builder: builder()[0]
        page = Page.objects.create(
            title="About",
            slug="about",
            status=Page.Status.PUBLISHED,
            published_content=self.content,
            cache_ttl=45,
        )

        response = self.client.get(f"/api/content/pages/{page.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "About")
        key, builder = cache.return_value.get_or_set_public.call_args.args
        self.assertEqual(key, "content:pages:about")
        # Storing vs. not storing is the cache's decision; the view's job is
        # to hand over the page's own `cache_ttl` with the payload.
        payload, ttl = builder()
        self.assertEqual(payload["title"], "About")
        self.assertEqual(ttl, 45)

    @patch("domains.content.views.CacheService")
    def test_zero_ttl_is_handed_over_and_the_page_still_renders(self, cache):
        cache.return_value.get_public.return_value = None
        cache.return_value.get_or_set_public.side_effect = lambda key, builder: builder()[0]
        Page.objects.create(
            title="Home",
            slug="home",
            status=Page.Status.PUBLISHED,
            published_content=self.content,
            cache_ttl=0,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Home")
        _, builder = cache.return_value.get_or_set_public.call_args.args
        self.assertEqual(builder()[1], 0)


class ContentCacheInvalidationTests(TestCase):
    @patch("domains.content.cache.CacheService")
    def test_direct_page_slug_update_invalidates_old_new_and_home_keys(self, cache):
        with self.captureOnCommitCallbacks(execute=True):
            page = Page.objects.create(title="Home", slug="home")
        cache.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            page.slug = "start"
            page.save()

        deleted = {call.args[0] for call in cache.return_value.delete_public.call_args_list}
        self.assertEqual(deleted, {"content:pages:home", "content:home", "content:pages:start"})

    @patch("domains.content.cache.CacheService")
    def test_direct_seo_change_invalidates_public_landing_page(self, cache):
        with self.captureOnCommitCallbacks(execute=True):
            page = LandingPage.objects.create(title="Sale", slug="sale")
        cache.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            SEORecord.objects.create(
                resource_type="landing_page", resource_id=page.id, title="Sale SEO"
            )

        cache.return_value.delete_public.assert_any_call("content:landing-pages:sale")
