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


class PageSEORecordAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="page-editor", password="password", is_staff=True
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_page")
        )
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="change_page")
        )
        self.client.force_authenticate(self.user)
        self.page = Page.objects.create(title="About Us", slug="about-us")

    def test_get_returns_null_when_no_seo_record(self):
        response = self.client.get(f"/api/content/admin/pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIsNone(response.data["data"])

    def test_put_creates_and_updates_page_seo(self):
        response = self.client.put(
            f"/api/content/admin/pages/{self.page.id}/seo",
            {
                "title": "About Us",
                "description": "Learn about Charchu.",
                "canonical_url": "https://example.com/about-us",
                "index": True,
                "follow": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        record = SEORecord.objects.get(resource_type="page", resource_id=self.page.id)
        self.assertEqual(record.title, "About Us")
        self.assertEqual(record.canonical_url, "https://example.com/about-us")

        response = self.client.put(
            f"/api/content/admin/pages/{self.page.id}/seo",
            {"title": "Updated", "index": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.title, "Updated")
        self.assertFalse(record.index)
        self.assertEqual(SEORecord.objects.count(), 1)

    def test_delete_removes_page_seo(self):
        SEORecord.objects.create(
            resource_type="page", resource_id=self.page.id, title="Saved"
        )

        response = self.client.delete(f"/api/content/admin/pages/{self.page.id}/seo")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SEORecord.objects.filter(resource_type="page", resource_id=self.page.id).exists()
        )

    def test_missing_page_returns_404(self):
        response = self.client.get("/api/content/admin/pages/99999/seo")

        self.assertEqual(response.status_code, 404)

    def test_requires_page_change_permission_for_write(self):
        viewer = User.objects.create_user(username="viewer", is_staff=True)
        viewer.user_permissions.add(
            Permission.objects.get(content_type__app_label="content", codename="view_page")
        )
        self.client.force_authenticate(viewer)

        response = self.client.put(
            f"/api/content/admin/pages/{self.page.id}/seo",
            {"title": "Blocked"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SEORecord.objects.exists())


