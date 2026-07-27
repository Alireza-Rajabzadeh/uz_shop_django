from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from domains.catalog.models import Category, CategoryDetail, CategoryStatus


class CategoryWriteTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)
        self.status = CategoryStatus.objects.create(name="active")

    def test_create_category_with_optional_parent(self):
        parent = Category.objects.create(name="Electronics", status=self.status)

        response = self.client.post(
            "/api/catalog/categories",
            {"name": " Phones ", "parent": parent.id, "status": self.status.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(name="Phones")
        self.assertEqual(category.parent, parent)

    def test_create_rejects_normalized_duplicate(self):
        Category.objects.create(name="Electronics Store", status=self.status)

        response = self.client.post(
            "/api/catalog/categories",
            {"name": " electronics  store ", "status": self.status.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Category.objects.count(), 1)

    def test_update_excludes_current_category_from_duplicate_check(self):
        category = Category.objects.create(name="Phones", status=self.status)

        response = self.client.patch(
            f"/api/catalog/categories/{category.id}",
            {"name": "Phones"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_update_rejects_descendant_as_parent(self):
        parent = Category.objects.create(name="Electronics", status=self.status)
        child = Category.objects.create(name="Phones", parent=parent, status=self.status)

        response = self.client.patch(
            f"/api/catalog/categories/{parent.id}",
            {"parent": child.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent)

    def test_name_suggestions_return_ranked_matches_and_exact_flag(self):
        category = Category.objects.create(name="Smart Phones", status=self.status)
        Category.objects.create(name="Groceries", status=self.status)

        response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": "smart phone"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["exact_duplicate"])
        self.assertEqual(response.data["data"]["suggestions"][0]["id"], category.id)

        exact_response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": " SMART PHONES "},
        )
        self.assertTrue(exact_response.data["data"]["exact_duplicate"])

    def test_name_suggestions_exclude_edited_category(self):
        category = Category.objects.create(name="Smart Phones", status=self.status)

        response = self.client.get(
            "/api/catalog/categories/name-suggestions",
            {"name": "Smart Phones", "exclude_id": category.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["exact_duplicate"])
        self.assertEqual(response.data["data"]["suggestions"], [])


class CategoryDetailWriteTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_authenticate(self.user)

    def test_create_select_detail_normalizes_options(self):
        response = self.client.post(
            "/api/catalog/category-details",
            {
                "name": " Product Color ",
                "type": "select",
                "required": True,
                "options": " Red, Green , ,Blue ",
                "filterable": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        detail = CategoryDetail.objects.get(name="Product Color")
        self.assertEqual(detail.options, "Red,Green,Blue")

    def test_select_detail_requires_options(self):
        response = self.client.post(
            "/api/catalog/category-details",
            {"name": "Color", "type": "select", "options": " , "},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CategoryDetail.objects.exists())

    def test_text_and_number_details_clear_options(self):
        detail = CategoryDetail.objects.create(
            name="Weight",
            type="select",
            options="Light,Heavy",
        )

        response = self.client.patch(
            f"/api/catalog/category-details/{detail.id}",
            {"type": "number"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        detail.refresh_from_db()
        self.assertEqual(detail.options, "")

    def test_create_rejects_normalized_duplicate(self):
        CategoryDetail.objects.create(name="Product Color", type="text")

        response = self.client.post(
            "/api/catalog/category-details",
            {"name": " product  color ", "type": "number"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(CategoryDetail.objects.count(), 1)

    def test_update_excludes_current_detail_from_duplicate_check(self):
        detail = CategoryDetail.objects.create(name="Color", type="text")

        response = self.client.patch(
            f"/api/catalog/category-details/{detail.id}",
            {"name": "Color"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_name_suggestions_return_matches_and_exclude_current_detail(self):
        detail = CategoryDetail.objects.create(name="Product Color", type="select", options="Red")

        response = self.client.get(
            "/api/catalog/category-details/name-suggestions",
            {"name": "product colors"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["suggestions"][0]["id"], detail.id)

        excluded_response = self.client.get(
            "/api/catalog/category-details/name-suggestions",
            {"name": "Product Color", "exclude_id": detail.id},
        )
        self.assertFalse(excluded_response.data["data"]["exact_duplicate"])
        self.assertEqual(excluded_response.data["data"]["suggestions"], [])
