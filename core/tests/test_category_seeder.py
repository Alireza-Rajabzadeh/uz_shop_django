import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from core.management.seeders.categories import CategorySeeder
from domains.catalog.models import Category, CategoryStatus


class CategorySeederTests(TestCase):
    def write_manifest(self, directory, categories, category_count=None):
        path = Path(directory) / "categories.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": "test",
                    "category_count": category_count if category_count is not None else 2,
                    "categories": categories,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_seeder_is_idempotent_and_preserves_existing_categories(self):
        status = CategoryStatus.objects.create(id=1, name="active")
        legacy = Category.objects.create(name="Legacy", status=status)
        categories = [
            {
                "id": 1001,
                "name": "Root",
                "source_url": "/main/root/",
                "children": [
                    {
                        "id": 1002,
                        "name": "Child",
                        "source_url": "/search/category-child/",
                        "children": [],
                    }
                ],
            }
        ]

        with TemporaryDirectory() as directory:
            seeder = CategorySeeder(self.write_manifest(directory, categories))
            self.assertEqual(seeder.run(), 2)
            self.assertEqual(seeder.run(), 2)

        legacy.refresh_from_db()
        child = Category.objects.get(id=1002)
        self.assertEqual(legacy.name, "Legacy")
        self.assertEqual(child.parent_id, 1001)
        self.assertEqual(Category.objects.count(), 3)
        self.assertGreater(Category.objects.create(name="After Import", status=status).id, 1002)

    def test_seeder_rejects_duplicate_sibling_names_before_writing(self):
        categories = [
            {
                "id": 1001,
                "name": "Root",
                "source_url": "/main/root/",
                "children": [
                    {
                        "id": 1002,
                        "name": "Child",
                        "source_url": "/search/category-child/",
                        "children": [],
                    },
                    {
                        "id": 1003,
                        "name": " child ",
                        "source_url": "/search/category-other-child/",
                        "children": [],
                    },
                ],
            }
        ]

        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, categories, category_count=3)
            with self.assertRaisesMessage(ValueError, "Duplicate sibling category name"):
                CategorySeeder(path).run()

        self.assertFalse(Category.objects.exists())
