from rest_framework.test import APITestCase

from core.services import CacheService
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus

from ..cache import home_cache_key, invalidate_page
from ..models import LandingPage, Page, SEORecord
from ..services.landing_page_service import LandingPageService
from ..services.page_service import PageService
from .factories import storefront_business


class LandingPageDeliveryAPITests(APITestCase):
    def setUp(self):
        self.business = storefront_business()
        self.business.business_name = "Delivery Business"
        self.business.display_name = "Delivery Business"
        self.business.save()
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
            business=self.business,
            title="Archived", slug="archived", status=LandingPage.Status.ARCHIVED
        )

        self.assertEqual(LandingPageService().get_by_slug("archived"), archived)

    def test_public_returns_only_published_page_and_published_content(self):
        published = LandingPage.objects.create(
            business=self.business,
            title="Published",
            slug="published",
            status=LandingPage.Status.PUBLISHED,
            draft_content=self.draft_content,
            published_content=self.published_content,
        )
        LandingPage.objects.create(
            business=self.business,
            title="Draft", slug="draft", status=LandingPage.Status.DRAFT
        )

        response = self.client.get(f"/api/business-content/landing-pages/{published.slug}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"], self.published_content)
        self.assertEqual(
            self.client.get("/api/business-content/landing-pages/draft").status_code,
            404,
        )

    def test_public_landing_page_includes_its_seo_record(self):
        page = LandingPage.objects.create(
            business=self.business,
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

        response = self.client.get(f"/api/business-content/landing-pages/{page.slug}")

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
            business=self.business,
            title="Published",
            slug="no-seo-page",
            status=LandingPage.Status.PUBLISHED,
            published_content=self.published_content,
        )

        response = self.client.get(f"/api/business-content/landing-pages/{page.slug}")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["data"]["seo"])

    def test_missing_slug_returns_not_found(self):
        response = self.client.get("/api/business-content/landing-pages/missing")

        self.assertEqual(response.status_code, 404)

    def test_public_resolves_component_model_ids_and_preserves_selected_order(self):
        category_status = CategoryStatus.objects.create(name="active")
        first_category = Category.objects.create(
            name="First category", fa_name="دسته اول", status=category_status
        )
        second_category = Category.objects.create(
            name="Second category", fa_name="دسته دوم", status=category_status
        )
        content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [
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
            business=self.business,
            title="Resolved",
            slug="resolved",
            status=LandingPage.Status.PUBLISHED,
            published_content=content,
        )

        response = self.client.get(f"/api/business-content/landing-pages/{page.slug}")

        self.assertEqual(response.status_code, 200)
        components = response.data["data"]["content"]["components"]
        self.assertEqual([item["id"] for item in components], ["categories"])
        self.assertEqual(
            [item["name"] for item in components[0]["props"]["categories"]],
            ["دسته دوم", "دسته اول"],
        )
        page.refresh_from_db()
        self.assertEqual(
            page.published_content["components"][0]["props"]["categories"],
            [second_category.id, first_category.id],
        )
