from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APITestCase

from domains.catalog.category_icons import match_category_icon
from domains.catalog.models import Category, CategoryStatus


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

    def test_create_allows_same_normalized_name_under_different_parents(self):
        first_parent = Category.objects.create(name="Home", status=self.status)
        second_parent = Category.objects.create(name="Baby", status=self.status)
        Category.objects.create(name="Towel", parent=first_parent, status=self.status)

        response = self.client.post(
            "/api/catalog/categories",
            {"name": " towel ", "parent": second_parent.id, "status": self.status.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Category.objects.filter(name__iexact="Towel").count(), 2)

    def test_update_excludes_current_category_from_duplicate_check(self):
        category = Category.objects.create(name="Phones", status=self.status)

        response = self.client.patch(
            f"/api/catalog/categories/{category.id}",
            {"name": "Phones"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_category_icon_matching_and_assignment_leave_unknown_names_empty(self):
        mobile = Category.objects.create(name="لوازم جانبی موبایل", status=self.status)
        unknown = Category.objects.create(name="Unclassified", status=self.status)

        self.assertEqual(match_category_icon(mobile.name), "device-mobile")
        self.assertIsNone(match_category_icon(unknown.name))
        call_command("assign_category_icons")

        mobile.refresh_from_db()
        unknown.refresh_from_db()
        self.assertEqual(mobile.logo, "device-mobile")
        self.assertIsNone(unknown.logo)

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
