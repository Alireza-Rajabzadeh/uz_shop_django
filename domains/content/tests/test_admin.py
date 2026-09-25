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


class ContentAdminAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="content-editor", password="password", is_staff=True
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="add_landingpage")
        )
        self.client.force_authenticate(self.user)

    def test_create_rejects_unknown_component(self):
        response = self.client.post(
            "/api/content/admin/landing-pages",
            {
                "title": "Home",
                "slug": "home",
                "draft_content": {
                    "schema_version": 1,
                    "contract_version": 4,
                    "components": [{"id": "x", "key": "unknown", "version": 1, "props": {}}],
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LandingPage.objects.exists())

    def test_create_defaults_draft_envelope(self):
        response = self.client.post(
            "/api/content/admin/landing-pages",
            {"title": "Home", "slug": "home"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["draft_content"], empty_draft_content())

    def test_retrieve_landing_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_landingpage")
        )
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.get(f"/api/content/admin/landing-pages/{page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["id"], page.id)
        self.assertEqual(response.data["data"]["title"], "Home")
        self.assertEqual(response.data["data"]["resolved_draft_content"], {})

    def test_patch_landing_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_landingpage")
        )
        page = LandingPage.objects.create(title="Home", slug="home")
        draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

        response = self.client.patch(
            f"/api/content/admin/landing-pages/{page.id}",
            {"title": "New Home", "draft_content": draft_content},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertEqual(page.title, "New Home")
        self.assertEqual(page.draft_content, draft_content)
        self.assertEqual(response.data["data"]["draft_content"], draft_content)

    def test_patch_rejects_invalid_draft_content(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_landingpage")
        )
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.patch(
            f"/api/content/admin/landing-pages/{page.id}",
            {
                "draft_content": {
                    "schema_version": 1,
                    "contract_version": 4,
                    "components": [
                        {"id": "x", "key": "unknown", "version": 1, "props": {}}
                    ],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        page.refresh_from_db()
        self.assertEqual(page.draft_content, {})

    def test_patch_requires_change_permission(self):
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.patch(
            f"/api/content/admin/landing-pages/{page.id}",
            {"title": "New Home"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.title, "Home")

    def test_delete_removes_landing_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="content", codename="delete_landingpage"
            )
        )
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.delete(f"/api/content/admin/landing-pages/{page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LandingPage.objects.filter(id=page.id).exists())

    def test_delete_requires_delete_permission(self):
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.delete(f"/api/content/admin/landing-pages/{page.id}")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(LandingPage.objects.filter(id=page.id).exists())

    def test_publish_promotes_draft_content_and_sets_published_at(self):
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="content", codename="change_landingpage"
            )
        )
        draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [
                {
                    "id": "banner",
                    "key": "small_banner",
                    "version": 1,
                    "props": {"items": [{"link": "/x", "title": "X"}]},
                }
            ],
        }
        page = LandingPage.objects.create(
            title="Home", slug="home", status=LandingPage.Status.DRAFT,
            draft_content=draft_content,
        )

        response = self.client.post(
            f"/api/content/admin/landing-pages/{page.id}/publish"
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertEqual(page.status, LandingPage.Status.PUBLISHED)
        self.assertEqual(page.published_content, draft_content)
        self.assertIsNotNone(page.published_at)

    def test_publish_requires_change_permission(self):
        page = LandingPage.objects.create(title="Home", slug="home")

        response = self.client.post(
            f"/api/content/admin/landing-pages/{page.id}/publish"
        )

        self.assertEqual(response.status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.status, LandingPage.Status.DRAFT)

    def test_retrieve_resolves_saved_products_regardless_of_product_status(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_landingpage")
        )
        product_status = ProductStatus.objects.create(name="inactive-authoring-test")
        product = Product.objects.create(name="Hidden product", status=product_status)
        draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [
                {
                    "id": "products",
                    "key": "product_slider",
                    "version": 1,
                    "props": {"title": "Products", "items": [product.id]},
                }
            ],
        }
        page = LandingPage.objects.create(
            title="Home", slug="home-products", draft_content=draft_content
        )

        response = self.client.get(f"/api/content/admin/landing-pages/{page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["draft_content"]["components"][0]["props"]["items"],
            [product.id],
        )
        self.assertEqual(
            response.data["data"]["resolved_draft_content"]["components"][0]["props"]["items"],
            [{
                "id": product.id,
                "name": "Hidden product",
                "thumbnail_url": None,
                "category_name": None,
                "category_fa_name": None,
                "status_name": "inactive-authoring-test",
            }],
        )

    def test_selector_requires_content_permission_and_returns_paginated_options(self):
        category_status = CategoryStatus.objects.create(name="active-content-test")
        product_status = ProductStatus.objects.create(name="published-content-test")
        category = Category.objects.create(name="Phones", status=category_status)
        product = Product.objects.create(
            name="Smart Phone", description="Current model", status=product_status
        )

        response = self.client.get("/api/content/admin/options/products?search=Smart&page=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(
            response.data["data"]["results"][0],
            {"id": product.id, "label": "Smart Phone", "description": "Current model"},
        )

        response = self.client.get("/api/content/admin/options/categories?search=Phones")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["results"], [{"id": category.id, "label": "Phones"}])

        denied = User.objects.create_user(username="other-staff", is_staff=True)
        self.client.force_authenticate(denied)
        self.assertEqual(self.client.get("/api/content/admin/options/products").status_code, 403)


class PageAdminAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="page-editor", password="password", is_staff=True
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="add_page")
        )
        self.client.force_authenticate(self.user)

    def test_create_defaults_draft_envelope(self):
        response = self.client.post(
            "/api/content/admin/pages",
            {"title": "About Us", "slug": "about-us"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["draft_content"], empty_draft_content())

    def test_retrieve_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_page")
        )
        page = Page.objects.create(title="About Us", slug="about-us")

        response = self.client.get(f"/api/content/admin/pages/{page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["id"], page.id)
        self.assertEqual(response.data["data"]["resolved_draft_content"], {})

    def test_patch_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_page")
        )
        page = Page.objects.create(title="About Us", slug="about-us")
        draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }

        response = self.client.patch(
            f"/api/content/admin/pages/{page.id}",
            {"title": "About Charchu", "draft_content": draft_content},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertEqual(page.title, "About Charchu")
        self.assertEqual(page.draft_content, draft_content)

    def test_patch_requires_change_permission(self):
        page = Page.objects.create(title="About Us", slug="about-us")

        response = self.client.patch(
            f"/api/content/admin/pages/{page.id}",
            {"title": "Renamed"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.title, "About Us")

    def test_delete_removes_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="delete_page")
        )
        page = Page.objects.create(title="About Us", slug="about-us")

        response = self.client.delete(f"/api/content/admin/pages/{page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Page.objects.filter(id=page.id).exists())

    def test_delete_requires_delete_permission(self):
        page = Page.objects.create(title="About Us", slug="about-us")

        response = self.client.delete(f"/api/content/admin/pages/{page.id}")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Page.objects.filter(id=page.id).exists())

    def test_publish_promotes_draft_content_and_sets_published_at(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_page")
        )
        draft_content = {
            "schema_version": 1,
            "contract_version": 4,
            "components": [],
        }
        page = Page.objects.create(
            title="About Us", slug="about-us", status=Page.Status.DRAFT,
            draft_content=draft_content,
        )

        response = self.client.post(f"/api/content/admin/pages/{page.id}/publish")

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertEqual(page.status, Page.Status.PUBLISHED)
        self.assertEqual(page.published_content, draft_content)
        self.assertIsNotNone(page.published_at)

    def test_publish_requires_change_permission(self):
        page = Page.objects.create(title="About Us", slug="about-us")

        response = self.client.post(f"/api/content/admin/pages/{page.id}/publish")

        self.assertEqual(response.status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.status, Page.Status.DRAFT)


