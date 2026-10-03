from rest_framework.test import APITestCase

from core.services import CacheService
from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus

from ..cache import HOME_CACHE_KEY, landing_page_cache_key
from ..contracts import empty_draft_content
from ..models import LandingPage, Page, SEORecord
from ..services import PageService, public_business_id
from .factories import storefront_business

CONTENT = {"schema_version": 1, "contract_version": 4, "components": []}


class VendorContentAPITests(APITestCase):
    """Business content authoring is scoped to the caller's business.

    Unlike `domains.content` there is no shared/admin scope: every row has a
    required owner. A vendor must only ever list, edit, publish, preview, and
    attach SEO to its own rows, and the public delivery routes serve only the
    singleton profile that backs the storefront.
    """

    def setUp(self):
        vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09127770001",
            password="pass1234",
            first_name="Content",
            last_name="Vendor",
            national_id="11227770001",
            status=vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09127770002",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="11227770002",
            status=vendor_status,
        )

        # The seeded singleton profile is the one `public_business_id()`
        # resolves, so this vendor adopts it as its storefront rather than
        # competing with a lower-pk row it does not own.
        self.business = storefront_business()
        self.business.vendor = self.vendor
        self.business.business_name = "Content Business"
        self.business.display_name = "Content Business"
        self.business.save()
        # An explicit pk: `inventory.0022` inserts id=1 directly, which never
        # advances the sequence, so a plain create() would collide with it.
        self.other_business = BusinessProfile.objects.create(
            id=9987,
            vendor=self.other_vendor,
            business_name="Other Content Business",
            display_name="Other Content Business",
        )

        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Content Phones", status=category_status
        )
        self.other_category = Category.objects.create(
            name="Other Content Phones", status=category_status
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)
        BusinessCategory.objects.create(
            business=self.other_business, category=self.other_category
        )

        product_status = ProductStatus.objects.create(name="active")
        self.product = Product.objects.create(name="Owned product", status=product_status)
        self.product.categories.add(self.category)
        self.foreign_product = Product.objects.create(
            name="Foreign product", status=product_status
        )
        self.foreign_product.categories.add(self.other_category)

        self.own_page = LandingPage.objects.create(
            title="Own landing", slug="own-landing", business=self.business
        )
        self.foreign_page = LandingPage.objects.create(
            title="Foreign landing",
            slug="foreign-landing",
            business=self.other_business,
        )

        self.client.force_authenticate(self.vendor)

    # ── list / create ────────────────────────────────────────────────

    def test_list_returns_only_own_business_rows(self):
        response = self.client.get("/api/business-content/vendor/landing-pages")

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["data"]["results"]
        self.assertEqual([row["slug"] for row in rows], ["own-landing"])
        self.assertEqual(rows[0]["business"], self.business.id)

    def test_create_assigns_caller_business(self):
        response = self.client.post(
            "/api/business-content/vendor/landing-pages",
            {"title": "New landing", "slug": "new-landing"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        page = LandingPage.objects.get(slug="new-landing")
        self.assertEqual(page.business_id, self.business.id)
        self.assertEqual(response.data["data"]["business"], self.business.id)
        self.assertEqual(
            response.data["data"]["draft_content"], empty_draft_content()
        )

    def test_slug_only_has_to_be_unique_inside_own_scope(self):
        # `foreign-landing` already exists in the other business's scope, and
        # `nobody-has-this` exists nowhere: both are fine for this caller.
        foreign = self.client.post(
            "/api/business-content/vendor/landing-pages",
            {"title": "Copy of foreign", "slug": "foreign-landing"},
            format="json",
        )
        fresh = self.client.post(
            "/api/business-content/vendor/landing-pages",
            {"title": "Fresh", "slug": "nobody-has-this"},
            format="json",
        )

        self.assertEqual(foreign.status_code, 201, foreign.data)
        self.assertEqual(fresh.status_code, 201, fresh.data)

    def test_create_rejects_duplicate_slug_inside_own_scope(self):
        response = self.client.post(
            "/api/business-content/vendor/landing-pages",
            {"title": "Copy", "slug": "own-landing"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            LandingPage.objects.filter(slug="own-landing", business=self.business).count(),
            1,
        )

    def test_create_rejects_missing_business_profile(self):
        BusinessProfile.objects.all().delete()

        response = self.client.post(
            "/api/business-content/vendor/landing-pages",
            {"title": "Orphan", "slug": "orphan-landing"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    # ── detail / publish / delete ────────────────────────────────────

    def test_foreign_rows_are_invisible_to_detail_mutations(self):
        url = f"/api/business-content/vendor/landing-pages/{self.foreign_page.id}"

        get_response = self.client.get(url)
        patch_response = self.client.patch(url, {"title": "Hijacked"}, format="json")
        delete_response = self.client.delete(url)

        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(patch_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.foreign_page.refresh_from_db()
        self.assertEqual(self.foreign_page.title, "Foreign landing")

    def test_patch_updates_own_row(self):
        response = self.client.patch(
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}",
            {"title": "Renamed landing"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.own_page.refresh_from_db()
        self.assertEqual(self.own_page.title, "Renamed landing")
        self.assertEqual(self.own_page.business_id, self.business.id)

    def test_publish_is_scoped(self):
        own_response = self.client.post(
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}/publish"
        )
        foreign_response = self.client.post(
            f"/api/business-content/vendor/landing-pages/{self.foreign_page.id}/publish"
        )

        self.assertEqual(own_response.status_code, 200, own_response.data)
        self.own_page.refresh_from_db()
        self.assertEqual(self.own_page.status, LandingPage.Status.PUBLISHED)
        self.assertEqual(foreign_response.status_code, 404)
        self.foreign_page.refresh_from_db()
        self.assertEqual(self.foreign_page.status, LandingPage.Status.DRAFT)

    def test_delete_removes_own_row_only(self):
        own_response = self.client.delete(
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}"
        )

        self.assertEqual(own_response.status_code, 200, own_response.data)
        self.assertFalse(LandingPage.objects.filter(id=self.own_page.id).exists())
        self.assertTrue(LandingPage.objects.filter(id=self.foreign_page.id).exists())

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        for url in (
            "/api/business-content/vendor/landing-pages",
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}",
        ):
            response = self.client.get(url)
            self.assertIn(response.status_code, (401, 403))

    # ── SEO ──────────────────────────────────────────────────────────

    def test_seo_is_scoped_to_owned_rows(self):
        own_response = self.client.put(
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}/seo",
            {"title": "Own SEO"},
            format="json",
        )
        foreign_response = self.client.put(
            f"/api/business-content/vendor/landing-pages/{self.foreign_page.id}/seo",
            {"title": "Foreign SEO"},
            format="json",
        )

        self.assertEqual(own_response.status_code, 200, own_response.data)
        record = SEORecord.objects.get(
            resource_type="landing_page", resource_id=self.own_page.id
        )
        self.assertEqual(record.title, "Own SEO")
        self.assertEqual(foreign_response.status_code, 404)
        self.assertFalse(
            SEORecord.objects.filter(
                resource_type="landing_page", resource_id=self.foreign_page.id
            ).exists()
        )

        get_foreign = self.client.get(
            f"/api/business-content/vendor/landing-pages/{self.foreign_page.id}/seo"
        )
        self.assertEqual(get_foreign.status_code, 404)

    # ── preview ──────────────────────────────────────────────────────

    def test_preview_is_scoped(self):
        own_response = self.client.get(
            f"/api/business-content/vendor/landing-pages/{self.own_page.id}/preview"
        )
        foreign_response = self.client.get(
            f"/api/business-content/vendor/landing-pages/{self.foreign_page.id}/preview"
        )

        self.assertEqual(own_response.status_code, 200, own_response.data)
        self.assertEqual(own_response.data["data"]["content"]["components"], [])
        self.assertEqual(foreign_response.status_code, 404)

    # ── pages ────────────────────────────────────────────────────────

    def test_page_endpoints_are_scoped(self):
        foreign = Page.objects.create(
            title="Foreign page", slug="foreign-page", business=self.other_business
        )

        list_response = self.client.get("/api/business-content/vendor/pages")
        self.assertEqual(list_response.status_code, 200, list_response.data)
        self.assertEqual(list_response.data["data"]["results"], [])

        foreign_detail = self.client.get(
            f"/api/business-content/vendor/pages/{foreign.id}"
        )
        self.assertEqual(foreign_detail.status_code, 404)

        create_response = self.client.post(
            "/api/business-content/vendor/pages",
            {"title": "My page", "slug": "my-page"},
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        page = Page.objects.get(slug="my-page", business=self.business)
        self.assertEqual(create_response.data["data"]["business"], page.business_id)

    # ── selector options ─────────────────────────────────────────────

    def test_product_options_only_offer_business_catalog(self):
        response = self.client.get("/api/business-content/vendor/options/products")

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["id"] for row in response.data["data"]["results"]]
        self.assertEqual(ids, [self.product.id])

    def test_category_options_only_offer_business_categories(self):
        response = self.client.get("/api/business-content/vendor/options/categories")

        self.assertEqual(response.status_code, 200, response.data)
        ids = [row["id"] for row in response.data["data"]["results"]]
        self.assertEqual(ids, [self.category.id])

    # ── component contracts ──────────────────────────────────────────

    def test_component_contracts_match_the_authoring_vocabulary(self):
        response = self.client.get("/api/business-content/vendor/component-contracts")

        self.assertEqual(response.status_code, 200, response.data)
        payload = response.data["data"]
        self.assertIs(type(payload["contract_version"]), int)
        self.assertIsInstance(payload["components"], list)
        self.assertTrue(
            any(
                component["key"] == "hero_slider"
                for component in payload["components"]
            )
        )

    def test_component_contracts_require_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/business-content/vendor/component-contracts")

        self.assertIn(response.status_code, (401, 403))

    # ── public delivery ──────────────────────────────────────────────

    def test_public_routes_serve_the_storefront_business_only(self):
        CacheService().delete_public(landing_page_cache_key("own-landing"))
        CacheService().delete_public(landing_page_cache_key("foreign-landing"))
        LandingPage.objects.filter(id=self.own_page.id).update(
            status=LandingPage.Status.PUBLISHED,
            published_content=CONTENT,
            cache_ttl=0,
        )
        LandingPage.objects.filter(id=self.foreign_page.id).update(
            status=LandingPage.Status.PUBLISHED,
            published_content=CONTENT,
            cache_ttl=0,
        )

        own_response = self.client.get("/api/business-content/landing-pages/own-landing")
        foreign_response = self.client.get(
            "/api/business-content/landing-pages/foreign-landing"
        )

        self.assertEqual(own_response.status_code, 200, own_response.data)
        self.assertEqual(foreign_response.status_code, 404)

    def test_public_business_id_resolves_the_storefront_profile(self):
        self.assertEqual(public_business_id(), self.business.id)

    def test_home_serves_the_storefront_business_home(self):
        CacheService().delete_public(HOME_CACHE_KEY)
        home = Page.objects.create(
            title="Storefront home",
            slug=PageService.HOME_SLUG,
            business=self.business,
            status=Page.Status.PUBLISHED,
            published_content=CONTENT,
            cache_ttl=0,
        )
        Page.objects.create(
            title="Other home",
            slug=PageService.HOME_SLUG,
            business=self.other_business,
            status=Page.Status.PUBLISHED,
            published_content=CONTENT,
            cache_ttl=0,
        )

        response = self.client.get("/api/business-content/home")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["id"], home.id)

    def test_home_returns_not_found_without_a_profile(self):
        CacheService().delete_public(HOME_CACHE_KEY)
        BusinessProfile.objects.all().delete()

        response = self.client.get("/api/business-content/home")

        self.assertEqual(response.status_code, 404)
