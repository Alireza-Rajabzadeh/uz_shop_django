import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import captured_stdout

from core.management.seeders.brands import BrandSeeder
from core.management.seeders.category_details import CategoryDetailSeeder
from core.management.seeders.variant_attributes import VariantAttributeSeeder
from domains.catalog.models import (
    Brand,
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryStatus,
    CategoryVariantAttribute,
    Product,
    ProductStatus,
    VariantAttribute,
    VariantOption,
)


class BrandSeederTests(TestCase):
    def write_manifest(self, directory, brands):
        path = Path(directory) / "brands.json"
        path.write_text(
            json.dumps({"schema_version": 1, "brands": brands}),
            encoding="utf-8",
        )
        return path

    def test_seeder_is_idempotent(self):
        with TemporaryDirectory() as directory:
            path = self.write_manifest(
                directory,
                [{"name": "Apple", "fa_name": "اپل"}, {"name": "Xiaomi", "fa_name": "شیائومی"}],
            )
            seeder = BrandSeeder(path)
            self.assertEqual(seeder.run(), 2)
            self.assertEqual(seeder.run(), 2)
        self.assertEqual(Brand.objects.count(), 2)
        self.assertEqual(Brand.objects.get(name="Apple").fa_name, "اپل")

    def test_seeder_updates_fa_name_and_normalized_matches(self):
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, [{"name": "Apple", "fa_name": "اپل"}])
            BrandSeeder(path).run()
            path = self.write_manifest(directory, [{"name": " apple ", "fa_name": "سیب"}])
            self.assertEqual(BrandSeeder(path).run(), 1)
        self.assertEqual(Brand.objects.count(), 1)
        self.assertEqual(Brand.objects.get().fa_name, "سیب")

    def test_seeder_rejects_duplicate_names(self):
        with TemporaryDirectory() as directory:
            path = self.write_manifest(
                directory,
                [{"name": "Apple"}, {"name": " apple "}],
            )
            with self.assertRaisesMessage(ValueError, "Duplicate brand name"):
                BrandSeeder(path).run()


class CategoryDetailSeederTests(TestCase):
    def setUp(self):
        status = CategoryStatus.objects.create(id=1, name="active")
        Category.objects.create(id=1001, name="موبایل", status=status)
        Category.objects.create(id=1003, name="شارژر گوشی", status=status)

    def write_manifest(self, directory, details, relations):
        path = Path(directory) / "category_details.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "details": details,
                    "relations": relations,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_seeder_creates_details_and_relations_idempotently(self):
        details = [{"name": "وزن", "type": "text"}]
        relations = [
            {"category_id": 1001, "detail": "وزن", "value": ""},
            {"category_id": 1003, "detail": "وزن", "value": ""},
        ]
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, details, relations)
            seeder = CategoryDetailSeeder(path)
            self.assertEqual(seeder.run(), 1)
            self.assertEqual(seeder.run(), 1)
        self.assertEqual(CategoryDetail.objects.count(), 1)
        self.assertEqual(CategoryDetailRelation.objects.count(), 2)

    def test_seeder_rejects_unknown_category(self):
        details = [{"name": "وزن", "type": "text"}]
        relations = [{"category_id": 9999, "detail": "وزن", "value": ""}]
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, details, relations)
            with self.assertRaisesMessage(ValueError, "do not exist"):
                CategoryDetailSeeder(path).run()
        self.assertFalse(CategoryDetail.objects.exists())

    def test_seeder_rejects_unknown_detail_reference(self):
        details = [{"name": "وزن", "type": "text"}]
        relations = [{"category_id": 1001, "detail": "ناموجود", "value": ""}]
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, details, relations)
            with self.assertRaisesMessage(ValueError, "unknown detail"):
                CategoryDetailSeeder(path).run()


class VariantAttributeSeederTests(TestCase):
    def setUp(self):
        status = CategoryStatus.objects.create(id=1, name="active")
        Category.objects.create(id=1001, name="موبایل", status=status)

    def write_manifest(self, directory, attributes):
        path = Path(directory) / "variant_attributes.json"
        path.write_text(
            json.dumps({"schema_version": 1, "attributes": attributes}),
            encoding="utf-8",
        )
        return path

    def test_seeder_creates_attributes_options_and_assignments_idempotently(self):
        attributes = [
            {
                "name": "Color",
                "options": [
                    {"name": "Black", "fa_name": "مشکی", "info": "#000000", "sku_code": "BLK"},
                ],
                "categories": [1001],
            }
        ]
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, attributes)
            seeder = VariantAttributeSeeder(path)
            self.assertEqual(seeder.run(), 1)
            self.assertEqual(seeder.run(), 1)
        self.assertEqual(VariantAttribute.objects.count(), 1)
        self.assertEqual(VariantOption.objects.count(), 1)
        self.assertEqual(CategoryVariantAttribute.objects.count(), 1)

    def test_seeder_rejects_duplicate_sku_codes(self):
        attributes = [
            {
                "name": "Color",
                "options": [
                    {"name": "Black", "sku_code": "BLK"},
                    {"name": "Blue", "sku_code": "blk"},
                ],
                "categories": [],
            }
        ]
        with TemporaryDirectory() as directory:
            path = self.write_manifest(directory, attributes)
            with self.assertRaisesMessage(ValueError, "Duplicate option SKU code"):
                VariantAttributeSeeder(path).run()


class CleanupTestDataCommandTests(TestCase):
    def setUp(self):
        status = CategoryStatus.objects.create(id=1, name="active")
        product_status, _ = ProductStatus.objects.get_or_create(name="pending")
        self.test_category = Category.objects.create(
            id=5, name="Test Category 005", status=status
        )
        self.real_category = Category.objects.create(
            id=1001, name="موبایل", status=status
        )
        test_product = Product.objects.create(
            name="Test Product 001", status=product_status
        )
        test_product.categories.add(self.test_category)
        real_product = Product.objects.create(
            name="گوشی واقعی", status=product_status
        )
        real_product.categories.add(self.real_category)
        self.test_detail = CategoryDetail.objects.create(name="Test Detail 001", type="text")
        self.real_detail = CategoryDetail.objects.create(name="وزن", type="text")
        CategoryDetailRelation.objects.create(
            category=self.real_category, detail=self.real_detail, value=""
        )

    def test_cleanup_removes_only_test_data(self):
        with captured_stdout():
            call_command("cleanup_test_data", "--yes")
        self.assertFalse(Product.objects.filter(name="Test Product 001").exists())
        self.assertTrue(Product.objects.filter(name="گوشی واقعی").exists())
        self.assertFalse(Category.objects.filter(pk=self.test_category.pk).exists())
        self.assertTrue(Category.objects.filter(pk=self.real_category.pk).exists())
        self.assertFalse(CategoryDetail.objects.filter(pk=self.test_detail.pk).exists())
        self.assertTrue(CategoryDetail.objects.filter(pk=self.real_detail.pk).exists())
        self.assertEqual(CategoryDetailRelation.objects.count(), 1)

    def test_cleanup_is_noop_when_nothing_to_remove(self):
        with captured_stdout():
            call_command("cleanup_test_data", "--yes")
        with captured_stdout():
            call_command("cleanup_test_data", "--yes")
        self.assertTrue(Category.objects.filter(pk=self.real_category.pk).exists())
