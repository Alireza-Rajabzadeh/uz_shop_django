from django.test import TestCase

from core.management.seeders.product_statuses import ProductStatusSeeder
from domains.catalog.models import ProductStatus


class ProductStatusSeederTests(TestCase):
    def setUp(self):
        self.seeder = ProductStatusSeeder()

    def test_seeder_creates_all_statuses(self):
        self.seeder.run()
        names = set(
            ProductStatus.objects.values_list("name", flat=True)
        )
        expected = {
            "active", "inactive", "pending", "preorder",
            "wait_for_admin_confirmation", "admin_rejected",
        }
        self.assertEqual(names, expected)

    def test_seeder_creates_six_statuses(self):
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)

    def test_seeder_is_idempotent(self):
        self.seeder.run()
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)

    def test_seeder_preserves_existing_ids(self):
        status, _ = ProductStatus.objects.get_or_create(name="pending")
        original_id = status.pk
        self.seeder.run()
        status.refresh_from_db()
        self.assertEqual(status.pk, original_id)

    def test_seeder_normalizes_casing(self):
        ProductStatus.objects.create(name="ACTIVE")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)
        status = ProductStatus.objects.get(name="active")
        self.assertIsNotNone(status)

    def test_seeder_normalizes_casing_for_wait_for_admin_confirmation(self):
        ProductStatus.objects.create(name="WAIT_FOR_ADMIN_CONFIRMATION")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)
        status = ProductStatus.objects.get(name="wait_for_admin_confirmation")
        self.assertIsNotNone(status)

    def test_seeder_normalizes_casing_for_admin_rejected(self):
        ProductStatus.objects.create(name="ADMIN_REJECTED")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)
        status = ProductStatus.objects.get(name="admin_rejected")
        self.assertIsNotNone(status)

    def test_seeder_creates_vendor_statuses_alongside_existing(self):
        ProductStatus.objects.get_or_create(name="pending")
        ProductStatus.objects.get_or_create(name="active")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)

    def test_seeder_does_not_duplicate_on_multiple_runs(self):
        for _ in range(5):
            self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 6)

    def test_seeder_all_statuses_are_lowercase(self):
        self.seeder.run()
        for status in ProductStatus.objects.all():
            self.assertEqual(status.name, status.name.lower())

    def test_seeder_wait_for_admin_confirmation_exists(self):
        self.seeder.run()
        self.assertTrue(
            ProductStatus.objects.filter(
                name="wait_for_admin_confirmation"
            ).exists()
        )

    def test_seeder_admin_rejected_exists(self):
        self.seeder.run()
        self.assertTrue(
            ProductStatus.objects.filter(
                name="admin_rejected"
            ).exists()
        )

    def test_seeder_vendor_statuses_have_unique_names(self):
        self.seeder.run()
        names = list(ProductStatus.objects.values_list("name", flat=True))
        self.assertEqual(len(names), len(set(names)))
