from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from domains.catalog.models import Category, CategoryStatus


class StorefrontStaticDataTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.active = CategoryStatus.objects.create(name="active")
        self.inactive = CategoryStatus.objects.create(name="inactive")
        self.pending = CategoryStatus.objects.create(name="pending")

    def create_category(self, name, *, status=None, parent=None, **values):
        return Category.objects.create(
            name=name,
            status=status or self.active,
            parent=parent,
            **values,
        )

    @patch("domains.catalog.api.static_data.cache_service")
    def test_categories_are_rebuilt_cached_and_returned(self, cache_service):
        root = self.create_category("Electronics", fa_name="الکترونیک", logo="cpu")
        child = self.create_category("Phones", parent=root)
        self.create_category("Smartphones", parent=child)
        hidden_root = self.create_category("Hidden", status=self.inactive)
        self.create_category("Hidden child", parent=hidden_root)
        self.create_category("Pending", status=self.pending)

        with self.assertNumQueries(1):
            response = self.client.get("/api/catalog/statics", {"data": "categories"})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(response.data["data"]), ["categories"])
        categories = response.data["data"]["categories"]
        self.assertEqual([category["id"] for category in categories], [root.id])
        self.assertEqual(categories[0]["name"], "الکترونیک")
        self.assertEqual(categories[0]["icon"], "cpu")
        self.assertEqual(categories[0]["children"][0]["id"], child.id)
        self.assertEqual(
            categories[0]["children"][0]["children"][0]["name"],
            "Smartphones",
        )
        cache_service.put_public.assert_called_once_with("categories", categories)

    @patch("domains.catalog.api.static_data.cache_service")
    def test_request_without_data_processes_all_handlers(self, cache_service):
        category = self.create_category("Books")

        response = self.client.get("/api/catalog/statics")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["data"]["categories"][0]["id"],
            category.id,
        )
        cache_service.put_public.assert_called_once()

    @override_settings(DEBUG=False)
    @patch("domains.catalog.api.static_data.cache_service")
    def test_unsupported_data_uses_normal_validation_response(self, cache_service):
        response = self.client.get("/api/catalog/statics", {"data": "brands"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("data", response.data["errors"])
        cache_service.put_public.assert_not_called()

    @patch("domains.catalog.api.static_data.cache_service")
    def test_each_request_rebuilds_from_the_database(self, cache_service):
        first = self.create_category("First")
        initial = self.client.get("/api/catalog/statics", {"data": "categories"})
        second = self.create_category("Second")

        refreshed = self.client.get("/api/catalog/statics", {"data": "categories"})

        self.assertEqual(
            [item["id"] for item in initial.data["data"]["categories"]],
            [first.id],
        )
        self.assertEqual(
            [item["id"] for item in refreshed.data["data"]["categories"]],
            [first.id, second.id],
        )
        self.assertEqual(cache_service.put_public.call_count, 2)

    @patch("domains.catalog.api.static_data.cache_service")
    def test_cache_write_failure_does_not_fail_the_api(self, cache_service):
        cache_service.put_public.return_value = False
        self.create_category("Available")

        response = self.client.get("/api/catalog/statics", {"data": "categories"})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["data"]["categories"]), 1)
