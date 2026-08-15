from django.contrib.auth.models import Permission, User
from rest_framework import serializers
from rest_framework.test import APITestCase

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage


class DraftContentValidationTests(APITestCase):
    def test_empty_draft_normalizes_to_versioned_envelope(self):
        self.assertEqual(
            validate_draft_content({}),
            {"schema_version": 1, "contract_version": 3, "components": []},
        )

    def test_rejects_duplicate_component_ids_and_invalid_props(self):
        component = {
            "id": "banner-1",
            "key": "small_banner",
            "version": 1,
            "props": {"items": [{"link": "/sale", "title": "Sale"}]},
        }
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content({
                "schema_version": 1,
                "contract_version": 3,
                "components": [component, component],
            })

        component["props"] = {"items": [{"link": 4, "title": "Sale"}]}
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content({
                "schema_version": 1,
                "contract_version": 3,
                "components": [component],
            })

    def test_accepts_model_ids_and_rejects_empty_required_selection(self):
        component = {
            "id": "products-1",
            "key": "product_slider",
            "version": 1,
            "props": {"title": "Featured", "items": [4, 8]},
        }
        content = {
            "schema_version": 1,
            "contract_version": 3,
            "components": [component],
        }
        self.assertEqual(validate_draft_content(content), content)

        component["props"]["items"] = []
        with self.assertRaises(serializers.ValidationError):
            validate_draft_content(content)


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
                    "contract_version": 3,
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

    def test_patch_landing_page(self):
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_landingpage")
        )
        page = LandingPage.objects.create(title="Home", slug="home")
        draft_content = {
            "schema_version": 1,
            "contract_version": 3,
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
                    "contract_version": 3,
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
