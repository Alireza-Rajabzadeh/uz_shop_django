from unittest.mock import patch

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
from domains.storefront.cache import (
    LAYOUT_CACHE_TTL,
    invalidate_layout_cache,
    invalidate_page_cache,
    layout_cache_key,
    page_cache_key,
)


class StorefrontPageCacheTests(APITestCase):
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
            business_name="cache-shop",
            display_name="Cache Shop",
            status=cls.active_status,
        )
        cls.subdomain = BusinessSubdomain.objects.create(
            business=cls.business,
            subdomain="cache-shop",
            status=cls.active_sub_status,
        )

        content_payload = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

        cls.platform_page = ContentPage.objects.create(
            title="Platform Page",
            slug="platform-page",
            status=ContentPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
            cache_ttl=120,
        )
        cls.platform_zero_ttl = ContentPage.objects.create(
            title="Zero TTL Page",
            slug="zero-ttl",
            status=ContentPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
            cache_ttl=0,
        )

        cls.business_page = BusinessPage.objects.create(
            business=cls.business,
            title="Business Page",
            slug="biz-page",
            status=BusinessPage.Status.PUBLISHED,
            published_content=content_payload,
            draft_content=content_payload,
            cache_ttl=240,
        )

    def test_cache_key_generation(self):
        self.assertEqual(
            page_cache_key("home"),
            "storefront:page:home:platform",
        )
        self.assertEqual(
            page_cache_key("about", business_id=None),
            "storefront:page:about:platform",
        )
        self.assertEqual(
            page_cache_key("home", business_id=self.business.id),
            f"storefront:page:home:{self.business.id}",
        )
        self.assertEqual(
            page_cache_key("home", business_id=self.business),
            f"storefront:page:home:{self.business.id}",
        )

    @patch("domains.storefront.views.page.ContentPageService")
    @patch("domains.storefront.views.page.CacheService")
    def test_platform_page_cache_hit_bypasses_service(self, cache_mock, service_mock):
        cached_payload = {"title": "Cached Platform", "slug": "platform-page"}
        cache_mock.return_value.get_public.return_value = cached_payload

        response = self.client.get("/api/v1/storefront/page/platform-page")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"], cached_payload)
        cache_mock.return_value.get_public.assert_called_once_with(
            "storefront:page:platform-page:platform"
        )
        service_mock.assert_not_called()

    @patch("domains.storefront.views.page.BusinessPageService")
    @patch("domains.storefront.views.page.CacheService")
    def test_business_page_cache_hit_bypasses_service(self, cache_mock, service_mock):
        cached_payload = {"title": "Cached Business", "slug": "biz-page"}
        cache_mock.return_value.get_public.return_value = cached_payload

        response = self.client.get(
            "/api/v1/storefront/page/biz-page",
            HTTP_X_TENANT_SUBDOMAIN="cache-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"], cached_payload)
        cache_mock.return_value.get_public.assert_called_once_with(
            f"storefront:page:biz-page:{self.business.id}"
        )
        service_mock.assert_not_called()

    @patch("domains.storefront.views.page.CacheService")
    def test_platform_page_cache_miss_stores_data_in_cache(self, cache_mock):
        cache_mock.return_value.get_public.return_value = None

        response = self.client.get("/api/v1/storefront/page/platform-page")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Platform Page")

        cache_mock.return_value.get_public.assert_called_once_with(
            "storefront:page:platform-page:platform"
        )
        cache_mock.return_value.put_public.assert_called_once_with(
            "storefront:page:platform-page:platform",
            response.data["data"],
            ttl=120,
        )

    @patch("domains.storefront.views.page.CacheService")
    def test_business_page_cache_miss_stores_data_in_cache(self, cache_mock):
        cache_mock.return_value.get_public.return_value = None

        response = self.client.get(
            "/api/v1/storefront/page/biz-page",
            HTTP_X_TENANT_SUBDOMAIN="cache-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Business Page")

        expected_key = f"storefront:page:biz-page:{self.business.id}"
        cache_mock.return_value.get_public.assert_called_once_with(expected_key)
        cache_mock.return_value.put_public.assert_called_once_with(
            expected_key,
            response.data["data"],
            ttl=240,
        )

    @patch("domains.storefront.views.page.CacheService")
    def test_zero_ttl_page_is_not_stored_in_cache(self, cache_mock):
        cache_mock.return_value.get_public.return_value = None

        response = self.client.get("/api/v1/storefront/page/zero-ttl")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["title"], "Zero TTL Page")

        cache_mock.return_value.get_public.assert_called_once_with(
            "storefront:page:zero-ttl:platform"
        )
        cache_mock.return_value.put_public.assert_not_called()

    @patch("domains.storefront.cache.CacheService")
    def test_invalidate_page_cache_helper(self, cache_mock):
        invalidate_page_cache("home")
        cache_mock.return_value.delete_public.assert_called_once_with(
            "storefront:page:home:platform"
        )

        cache_mock.return_value.delete_public.reset_mock()
        invalidate_page_cache("home", business_id=self.business.id)
        cache_mock.return_value.delete_public.assert_called_once_with(
            f"storefront:page:home:{self.business.id}"
        )

    @patch("domains.storefront.cache.CacheService")
    def test_content_page_update_invalidates_storefront_cache(self, cache_mock):
        with self.captureOnCommitCallbacks(execute=True):
            self.platform_page.title = "Updated Title"
            self.platform_page.save()

        cache_mock.return_value.delete_public.assert_any_call(
            "storefront:page:platform-page:platform"
        )

    @patch("domains.storefront.cache.CacheService")
    def test_content_page_rename_invalidates_both_old_and_new_slugs(self, cache_mock):
        page = ContentPage.objects.create(
            title="Temp Page",
            slug="temp-slug",
            status=ContentPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        cache_mock.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            page.slug = "new-slug"
            page.save()

        deleted = {call.args[0] for call in cache_mock.return_value.delete_public.call_args_list}
        self.assertIn("storefront:page:temp-slug:platform", deleted)
        self.assertIn("storefront:page:new-slug:platform", deleted)

    @patch("domains.storefront.cache.CacheService")
    def test_business_page_update_invalidates_storefront_cache(self, cache_mock):
        with self.captureOnCommitCallbacks(execute=True):
            self.business_page.title = "Updated Biz Page"
            self.business_page.save()

        expected_key = f"storefront:page:biz-page:{self.business.id}"
        cache_mock.return_value.delete_public.assert_any_call(expected_key)

    @patch("domains.storefront.cache.CacheService")
    def test_business_page_rename_invalidates_both_old_and_new_slugs(self, cache_mock):
        page = BusinessPage.objects.create(
            business=self.business,
            title="Biz Temp",
            slug="biz-temp-slug",
            status=BusinessPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        cache_mock.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            page.slug = "biz-new-slug"
            page.save()

        deleted = {call.args[0] for call in cache_mock.return_value.delete_public.call_args_list}
        self.assertIn(f"storefront:page:biz-temp-slug:{self.business.id}", deleted)
        self.assertIn(f"storefront:page:biz-new-slug:{self.business.id}", deleted)

    @patch("domains.storefront.cache.CacheService")
    def test_page_delete_invalidates_storefront_cache(self, cache_mock):
        page = ContentPage.objects.create(
            title="Delete Page",
            slug="to-delete",
            status=ContentPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        cache_mock.return_value.delete_public.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            page.delete()

        cache_mock.return_value.delete_public.assert_any_call(
            "storefront:page:to-delete:platform"
        )

    def test_layout_cache_key_generation(self):
        self.assertEqual(layout_cache_key(), "storefront:layout:platform")
        self.assertEqual(layout_cache_key(business_id=None), "storefront:layout:platform")
        self.assertEqual(
            layout_cache_key(business_id=self.business.id),
            f"storefront:layout:{self.business.id}",
        )
        self.assertEqual(
            layout_cache_key(business_id=self.business),
            f"storefront:layout:{self.business.id}",
        )

    @patch("domains.storefront.views.layout.StorefrontLayoutService")
    @patch("domains.storefront.views.layout.CacheService")
    def test_platform_layout_cache_hit_bypasses_service(self, cache_mock, service_mock):
        cached_payload = {"header": {}, "categories": [], "cached": True}
        cache_mock.return_value.get_public.return_value = cached_payload

        response = self.client.get("/api/v1/storefront/layout")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"], cached_payload)
        cache_mock.return_value.get_public.assert_called_once_with(
            "storefront:layout:platform"
        )
        service_mock.assert_not_called()

    @patch("domains.storefront.views.layout.StorefrontLayoutService")
    @patch("domains.storefront.views.layout.CacheService")
    def test_business_layout_cache_hit_bypasses_service(self, cache_mock, service_mock):
        cached_payload = {"header": {"business_id": self.business.id}, "cached": True}
        cache_mock.return_value.get_public.return_value = cached_payload

        response = self.client.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="cache-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"], cached_payload)
        cache_mock.return_value.get_public.assert_called_once_with(
            f"storefront:layout:{self.business.id}"
        )
        service_mock.assert_not_called()

    @patch("domains.storefront.views.layout.CacheService")
    def test_platform_layout_cache_miss_stores_data_in_cache(self, cache_mock):
        cache_mock.return_value.get_public.return_value = None

        response = self.client.get("/api/v1/storefront/layout")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        cache_mock.return_value.get_public.assert_called_once_with(
            "storefront:layout:platform"
        )
        cache_mock.return_value.put_public.assert_called_once_with(
            "storefront:layout:platform",
            response.data["data"],
            ttl=LAYOUT_CACHE_TTL,
        )

    @patch("domains.storefront.views.layout.CacheService")
    def test_business_layout_cache_miss_stores_data_in_cache(self, cache_mock):
        cache_mock.return_value.get_public.return_value = None

        response = self.client.get(
            "/api/v1/storefront/layout",
            HTTP_X_TENANT_SUBDOMAIN="cache-shop",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        expected_key = f"storefront:layout:{self.business.id}"
        cache_mock.return_value.get_public.assert_called_once_with(expected_key)
        cache_mock.return_value.put_public.assert_called_once_with(
            expected_key,
            response.data["data"],
            ttl=LAYOUT_CACHE_TTL,
        )

    @patch("domains.storefront.cache.CacheService")
    def test_invalidate_layout_cache_helper(self, cache_mock):
        invalidate_layout_cache()
        cache_mock.return_value.delete_public.assert_called_once_with(
            "storefront:layout:platform"
        )

        cache_mock.return_value.delete_public.reset_mock()
        invalidate_layout_cache(business_id=self.business.id)
        cache_mock.return_value.delete_public.assert_called_once_with(
            f"storefront:layout:{self.business.id}"
        )

    @patch("domains.storefront.cache.CacheService")
    def test_footer_page_change_invalidates_storefront_layout_cache(self, cache_mock):
        page = ContentPage.objects.create(
            title="Footer Page",
            slug="footer",
            status=ContentPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        cache_mock.return_value.delete_public.assert_any_call("storefront:layout:platform")

        cache_mock.return_value.delete_public.reset_mock()
        biz_page = BusinessPage.objects.create(
            business=self.business,
            title="Biz Footer",
            slug="footer",
            status=BusinessPage.Status.PUBLISHED,
            published_content={"schema_version": 1, "contract_version": 4, "components": []},
            draft_content={"schema_version": 1, "contract_version": 4, "components": []},
        )
        cache_mock.return_value.delete_public.assert_any_call(
            f"storefront:layout:{self.business.id}"
        )


