from django.contrib.auth.models import Permission, User
from rest_framework import serializers
from rest_framework.test import APITestCase

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage, SEORecord
from .services import LandingPageService


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
        self.assertEqual(response.data["data"]["resolved_draft_content"], {})

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
            "contract_version": 3,
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
            "contract_version": 3,
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


class SEORecordAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="content-editor", password="password", is_staff=True
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_landingpage")
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_landingpage")
        )
        self.client.force_authenticate(self.user)
        self.page = LandingPage.objects.create(title="Home", slug="home")

    def test_get_returns_null_when_no_seo_record(self):
        response = self.client.get(f"/api/content/admin/landing-pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["data"])

    def test_put_creates_seo_record(self):
        response = self.client.put(
            f"/api/content/admin/landing-pages/{self.page.id}/seo",
            {
                "title": "Home page",
                "description": "Shop everything.",
                "canonical_url": "https://example.com/home",
                "index": False,
                "follow": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        record = SEORecord.objects.get(
            resource_type="landing_page", resource_id=self.page.id
        )
        self.assertEqual(record.title, "Home page")
        self.assertEqual(record.canonical_url, "https://example.com/home")
        self.assertFalse(record.index)
        self.assertTrue(record.follow)
        self.assertEqual(response.data["data"]["title"], "Home page")

    def test_put_updates_existing_seo_record(self):
        record = SEORecord.objects.create(
            resource_type="landing_page",
            resource_id=self.page.id,
            title="Old title",
            index=True,
        )

        response = self.client.put(
            f"/api/content/admin/landing-pages/{self.page.id}/seo",
            {"title": "New title", "index": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.title, "New title")
        self.assertFalse(record.index)
        self.assertTrue(record.follow)
        self.assertEqual(SEORecord.objects.count(), 1)

    def test_get_returns_saved_seo_record(self):
        SEORecord.objects.create(
            resource_type="landing_page",
            resource_id=self.page.id,
            title="Saved title",
        )

        response = self.client.get(f"/api/content/admin/landing-pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Saved title")
        self.assertEqual(response.data["data"]["resource_type"], "landing_page")
        self.assertEqual(response.data["data"]["resource_id"], self.page.id)

    def test_delete_removes_seo_record(self):
        SEORecord.objects.create(
            resource_type="landing_page",
            resource_id=self.page.id,
            title="Saved title",
        )

        response = self.client.delete(f"/api/content/admin/landing-pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SEORecord.objects.filter(
                resource_type="landing_page", resource_id=self.page.id
            ).exists()
        )

    def test_delete_without_record_is_noop(self):
        response = self.client.delete(f"/api/content/admin/landing-pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SEORecord.objects.exists())

    def test_missing_landing_page_returns_404(self):
        response = self.client.get("/api/content/admin/landing-pages/99999/seo")

        self.assertEqual(response.status_code, 404)

    def test_requires_change_permission_for_write(self):
        viewer = User.objects.create_user(username="viewer", is_staff=True)
        viewer.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_landingpage")
        )
        self.client.force_authenticate(viewer)

        response = self.client.put(
            f"/api/content/admin/landing-pages/{self.page.id}/seo",
            {"title": "Blocked"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SEORecord.objects.exists())


class ProductSEORecordAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="product-editor", password="password", is_staff=True
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="catalog", codename="view_product")
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="catalog", codename="change_product")
        )
        self.client.force_authenticate(self.user)
        product_status = ProductStatus.objects.create(name="active-product-seo")
        self.product = Product.objects.create(
            name="Smart Phone", status=product_status
        )

    def test_get_returns_null_when_no_seo_record(self):
        response = self.client.get(f"/api/content/admin/products/{self.product.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["data"])

    def test_put_creates_and_updates_product_seo(self):
        response = self.client.put(
            f"/api/content/admin/products/{self.product.id}/seo",
            {
                "title": "Smart Phone",
                "description": "A great phone.",
                "canonical_url": "https://example.com/products/smart-phone",
                "index": True,
                "follow": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        record = SEORecord.objects.get(resource_type="product", resource_id=self.product.id)
        self.assertEqual(record.title, "Smart Phone")
        self.assertEqual(record.canonical_url, "https://example.com/products/smart-phone")

        response = self.client.put(
            f"/api/content/admin/products/{self.product.id}/seo",
            {"title": "Updated phone", "index": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.title, "Updated phone")
        self.assertFalse(record.index)
        self.assertEqual(SEORecord.objects.count(), 1)

    def test_delete_removes_product_seo(self):
        SEORecord.objects.create(
            resource_type="product", resource_id=self.product.id, title="Saved"
        )

        response = self.client.delete(f"/api/content/admin/products/{self.product.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SEORecord.objects.filter(resource_type="product", resource_id=self.product.id).exists()
        )

    def test_missing_product_returns_404(self):
        response = self.client.get("/api/content/admin/products/99999/seo")

        self.assertEqual(response.status_code, 404)

    def test_requires_catalog_change_permission_for_write(self):
        viewer = User.objects.create_user(username="viewer", is_staff=True)
        viewer.user_permissions.add(
            Permission.objects.get(content_type__app_label="catalog", codename="view_product")
        )
        self.client.force_authenticate(viewer)

        response = self.client.put(
            f"/api/content/admin/products/{self.product.id}/seo",
            {"title": "Blocked"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SEORecord.objects.exists())


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
            "contract_version": 3,
            "components": [self.second_component, self.first_component],
        }
        self.published_content = {
            "schema_version": 1,
            "contract_version": 3,
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

    def test_home_returns_published_home_landing_page_content(self):
        LandingPage.objects.create(
            title="Home",
            slug=LandingPageService.HOME_SLUG,
            status=LandingPage.Status.PUBLISHED,
            draft_content=self.draft_content,
            published_content=self.published_content,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"], self.published_content)
        self.assertEqual(response.data["data"]["slug"], LandingPageService.HOME_SLUG)

    def test_home_rejects_missing_or_unpublished_home_page(self):
        self.assertEqual(self.client.get("/api/content/home").status_code, 404)

        LandingPage.objects.create(
            title="Home draft",
            slug=LandingPageService.HOME_SLUG,
            status=LandingPage.Status.DRAFT,
            draft_content=self.draft_content,
        )
        self.assertEqual(self.client.get("/api/content/home").status_code, 404)

    def test_home_returns_empty_components_when_published_content_is_empty(self):
        LandingPage.objects.create(
            title="Home",
            slug=LandingPageService.HOME_SLUG,
            status=LandingPage.Status.PUBLISHED,
        )

        response = self.client.get("/api/content/home")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["content"]["components"], [])

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
            "contract_version": 3,
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
