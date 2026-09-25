from django.contrib.auth.models import Permission, User
from rest_framework import serializers
from rest_framework.test import APITestCase

from core.services import CacheService
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus

from ..contracts import (
    empty_draft_content,
    load_content_contracts,
    validate_contracts_payload,
    validate_draft_content,
)
from ..models import LandingPage, Page, SEORecord
from ..services import LandingPageService, PageService


class LandingPageDeliveryAPITests(APITestCase):
    def setUp(self):
        self.first_component = {
            "id": "first",
            "key": "small_banner",
            "version": 1,
            "props": {"items": [{"link": "/first", "title": "First"}]},
        }
        self.second_component = {
            "id": "second",
            "key": "small_banner",
            "version": 1,
            "props": {"items": [{"link": "/second", "title": "Second"}]},
        }
        self.draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [self.second_component, self.first_component],
        }
        self.published_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [self.first_component],
        }

    def test_service_retrieves_any_status_without_applying_access_rules(self):
        archived = LandingPage.objects.create(
            title="Archived", slug="archived", status=LandingPage.Status.ARCHIVED
        )

        self.assertEqual(LandingPageService().get_by_slug("archived"), archived)

    def test_preview_returns_draft_and_published_pages_with_draft_content(self):
        for status in (LandingPage.Status.DRAFT, LandingPage.Status.PUBLISHED):
            page = LandingPage.objects.create(
                title=status.title(),
                slug=f"page-{status}",
                status=status,
                draft_content=self.draft_content,
                published_content=self.published_content,
            )

            response = self.client.get(f"/api/content/landing-pages/{page.slug}/preview")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["data"]["content"], self.draft_content)
            self.assertEqual(
                [item["id"] for item in response.data["data"]["content"]["components"]],
                ["second", "first"],
            )

    def test_preview_rejects_archived_page(self):
        LandingPage.objects.create(
            title="Archived", slug="archived", status=LandingPage.Status.ARCHIVED
        )

        response = self.client.get("/api/content/landing-pages/archived/preview")

        self.assertEqual(response.status_code, 404)

    def test_public_returns_only_published_page_and_published_content(self):
        published = LandingPage.objects.create(
            title="Published",
            slug="published",
            status=LandingPage.Status.PUBLISHED,
            draft_content=self.draft_content,
            published_content=self.published_content,
        )
        LandingPage.objects.create(
            title="Draft", slug="draft", status=LandingPage.Status.DRAFT
        )

        response = self.client.get(f"/api/content/landing-pages/{published.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"], self.published_content)
        self.assertEqual(
            self.client.get("/api/content/landing-pages/draft").status_code,
            404,
        )

    def test_public_landing_page_includes_its_seo_record(self):
        page = LandingPage.objects.create(
            title="Published",
            slug="seo-page",
            status=LandingPage.Status.PUBLISHED,
            published_content=self.published_content,
        )
        SEORecord.objects.create(
            resource_type="landing_page",
            resource_id=page.id,
            title="SEO Landing",
            description="SEO description",
            canonical_url="https://example.com/seo-page",
            index=True,
            follow=False,
        )

        response = self.client.get(f"/api/content/landing-pages/{page.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        seo = response.data["data"]["seo"]
        self.assertEqual(seo["title"], "SEO Landing")
        self.assertEqual(seo["description"], "SEO description")
        self.assertEqual(seo["canonical_url"], "https://example.com/seo-page")
        self.assertIsNone(seo["image_id"])
        self.assertTrue(seo["index"])
        self.assertFalse(seo["follow"])

    def test_public_landing_page_returns_null_seo_without_record(self):
        page = LandingPage.objects.create(
            title="Published",
            slug="no-seo-page",
            status=LandingPage.Status.PUBLISHED,
            published_content=self.published_content,
        )

        response = self.client.get(f"/api/content/landing-pages/{page.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["data"]["seo"])

    def test_missing_slug_returns_not_found(self):
        response = self.client.get("/api/content/landing-pages/missing/preview")

        self.assertEqual(response.status_code, 404)

    def test_preview_resolves_component_model_ids_and_preserves_selected_order(self):
        category_status = CategoryStatus.objects.create(name="active")
        product_status = ProductStatus.objects.create(name="active")
        first_category = Category.objects.create(
            name="First category", fa_name="دسته اول", status=category_status
        )
        second_category = Category.objects.create(
            name="Second category", fa_name="دسته دوم", status=category_status
        )
        first_product = Product.objects.create(name="First product", status=product_status)
        second_product = Product.objects.create(name="Second product", status=product_status)
        first_product.categories.add(first_category)
        second_product.categories.add(second_category)
        content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [
                {
                    "id": "products",
                    "key": "product_slider",
                    "version": 1,
                    "props": {
                        "title": "Products",
                        "items": [second_product.id, first_product.id],
                    },
                },
                {
                    "id": "categories",
                    "key": "category_grid",
                    "version": 1,
                    "props": {
                        "categories": [second_category.id, first_category.id],
                    },
                },
            ],
        }
        page = LandingPage.objects.create(
            title="Resolved",
            slug="resolved",
            status=LandingPage.Status.DRAFT,
            draft_content=content,
        )

        response = self.client.get(f"/api/content/landing-pages/{page.slug}/preview")

        self.assertEqual(response.status_code, 200)
        components = response.data["data"]["content"]["components"]
        self.assertEqual([item["id"] for item in components], ["products", "categories"])
        self.assertEqual(
            [item["name"] for item in components[0]["props"]["items"]],
            ["Second product", "First product"],
        )
        self.assertEqual(
            [item["name"] for item in components[1]["props"]["categories"]],
            ["دسته دوم", "دسته اول"],
        )
        page.refresh_from_db()
        self.assertEqual(
            page.draft_content["components"][0]["props"]["items"],
            [second_product.id, first_product.id],
        )


class PageDeliveryAPITests(APITestCase):
    def setUp(self):
        CacheService().delete_public("content:home")
        self.content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

    def test_service_retrieves_any_status_without_applying_access_rules(self):
        archived = Page.objects.create(
            title="Archived", slug="archived", status=Page.Status.ARCHIVED
        )

        self.assertEqual(PageService().get_by_slug("archived"), archived)

    def test_preview_returns_draft_and_published_pages_with_draft_content(self):
        for status in (Page.Status.DRAFT, Page.Status.PUBLISHED):
            page = Page.objects.create(
                title=status.title(),
                slug=f"page-{status}",
                status=status,
                draft_content=self.content,
            )

            response = self.client.get(f"/api/content/pages/{page.slug}/preview")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["data"]["content"], self.content)
            self.assertEqual(response.data["data"]["slug"], page.slug)

    def test_preview_rejects_archived_page(self):
        Page.objects.create(
            title="Archived", slug="archived", status=Page.Status.ARCHIVED
        )

        response = self.client.get("/api/content/pages/archived/preview")

        self.assertEqual(response.status_code, 404)

    def test_public_returns_only_published_page_and_published_content(self):
        published = Page.objects.create(
            title="About Us",
            slug="about-us",
            status=Page.Status.PUBLISHED,
            draft_content=self.content,
            published_content=self.content,
        )
        Page.objects.create(title="Draft", slug="draft", status=Page.Status.DRAFT)

        response = self.client.get(f"/api/content/pages/{published.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"], self.content)
        self.assertEqual(
            self.client.get("/api/content/pages/draft").status_code,
            404,
        )

    def test_public_page_includes_its_seo_record(self):
        page = Page.objects.create(
            title="About Us",
            slug="about-us",
            status=Page.Status.PUBLISHED,
            published_content=self.content,
        )
        SEORecord.objects.create(
            resource_type="page",
            resource_id=page.id,
            title="SEO About",
            description="SEO description",
            metadata={"og_type": "website"},
        )

        response = self.client.get(f"/api/content/pages/{page.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        seo = response.data["data"]["seo"]
        self.assertEqual(seo["title"], "SEO About")
        self.assertEqual(seo["metadata"], {"og_type": "website"})
        self.assertIsNone(seo["canonical_url"])

    def test_home_includes_its_seo_record(self):
        home = Page.objects.create(
            title="Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content=self.content,
        )
        SEORecord.objects.create(
            resource_type="page",
            resource_id=home.id,
            title="Home SEO",
            description="Home description",
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200, response.data)
        seo = response.data["data"]["seo"]
        self.assertEqual(seo["title"], "Home SEO")
        self.assertEqual(seo["description"], "Home description")

    def test_home_returns_null_seo_without_record(self):
        Page.objects.create(
            title="Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            published_content=self.content,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["data"]["seo"])

    def test_home_returns_published_home_page_content(self):
        Page.objects.create(
            title="Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
            draft_content=self.content,
            published_content=self.content,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"], self.content)
        self.assertEqual(response.data["data"]["slug"], PageService.HOME_SLUG)

    def test_home_rejects_missing_or_unpublished_home_page(self):
        self.assertEqual(self.client.get("/api/content/home").status_code, 404)

        Page.objects.create(
            title="Home draft",
            slug=PageService.HOME_SLUG,
            status=Page.Status.DRAFT,
            draft_content=self.content,
        )
        self.assertEqual(self.client.get("/api/content/home").status_code, 404)

    def test_home_returns_empty_components_when_published_content_is_empty(self):
        Page.objects.create(
            title="Home",
            slug=PageService.HOME_SLUG,
            status=Page.Status.PUBLISHED,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"]["components"], [])

    def test_missing_slug_returns_not_found(self):
        response = self.client.get("/api/content/pages/missing")

        self.assertEqual(response.status_code, 404)
