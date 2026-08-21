from urllib.parse import quote

from django.contrib.auth.models import Permission, User
from rest_framework.test import APITestCase

from domains.catalog.models import Brand, Category, CategoryStatus

from .models import SEORecord


class CatalogResourceSEOAdminTests(APITestCase):
    def setUp(self):
        self.active = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(name="Phones", status=self.active)
        self.brand = Brand.objects.create(name="Acme")

    def authenticate(self, resource_type, *actions):
        user = User.objects.create_user(
            username=f"{resource_type}-{'-'.join(actions)}", is_staff=True
        )
        for action in actions:
            user.user_permissions.add(Permission.objects.get(
                content_type__app_label="catalog",
                codename=f"{action}_{resource_type}",
            ))
        self.client.force_authenticate(user)

    def test_category_admin_get_put_delete(self):
        self.authenticate("category", "view", "change")
        url = f"/api/content/admin/categories/{self.category.id}/seo"

        self.assertIsNone(self.client.get(url).data["data"])
        response = self.client.put(url, {"title": "Phone category"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(SEORecord.objects.filter(
            resource_type="category", resource_id=self.category.id
        ).exists())
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertFalse(SEORecord.objects.exists())

    def test_brand_admin_get_put_delete(self):
        self.authenticate("brand", "view", "change")
        url = f"/api/content/admin/brands/{self.brand.id}/seo"

        self.assertIsNone(self.client.get(url).data["data"])
        response = self.client.put(url, {"title": "Acme brand"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["resource_type"], "brand")
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_catalog_view_and_change_permissions_are_enforced(self):
        self.authenticate("category", "view")
        url = f"/api/content/admin/categories/{self.category.id}/seo"

        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.put(url, {"title": "Blocked"}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(url).status_code, 403)

    def test_missing_admin_resource_returns_404(self):
        self.authenticate("brand", "view")
        self.assertEqual(self.client.get("/api/content/admin/brands/999999/seo").status_code, 404)


class PublicCatalogResourceSEOTests(APITestCase):
    def setUp(self):
        self.active = CategoryStatus.objects.create(name="active")
        self.inactive = CategoryStatus.objects.create(name="inactive")

    def get_resource(self, resource_type, slug):
        return self.client.get(
            f"/api/content/seo/{resource_type}/{quote(slug, safe='')}"
        )

    def test_category_returns_identity_and_seo_without_authentication(self):
        category = Category.objects.create(name="Mobile Phones", status=self.active)
        SEORecord.objects.create(
            resource_type="category", resource_id=category.id, title="Shop phones"
        )

        response = self.get_resource("category", category.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["resource"], {
            "id": category.id, "slug": category.slug, "name": category.name,
        })
        self.assertEqual(response.data["data"]["seo"]["title"], "Shop phones")

    def test_brand_without_seo_returns_null(self):
        brand = Brand.objects.create(name="Acme")

        response = self.get_resource("brand", brand.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["resource"]["id"], brand.id)
        self.assertIsNone(response.data["data"]["seo"])

    def test_unicode_slug_is_supported(self):
        category = Category.objects.create(name="گوشی موبایل", status=self.active)

        response = self.get_resource("category", category.slug)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["resource"]["slug"], category.slug)

    def test_inactive_category_or_inactive_ancestor_returns_404(self):
        inactive = Category.objects.create(name="Hidden", status=self.inactive)
        parent = Category.objects.create(name="Hidden parent", status=self.inactive)
        child = Category.objects.create(name="Visible child", status=self.active, parent=parent)

        self.assertEqual(self.get_resource("category", inactive.slug).status_code, 404)
        self.assertEqual(self.get_resource("category", child.slug).status_code, 404)

    def test_unknown_type_or_resource_returns_404(self):
        self.assertEqual(self.get_resource("product", "anything").status_code, 404)
        self.assertEqual(self.get_resource("brand", "missing").status_code, 404)
