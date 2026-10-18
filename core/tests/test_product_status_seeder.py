from django.test import TestCase

from core.management.seeders.product_statuses import ProductStatusSeeder
from core.management.seeders.vendor_product_statuses import VendorProductStatusSeeder
from domains.catalog.models import ProductStatus, VendorProductStatus


class ProductStatusSeederTests(TestCase):
    def setUp(self):
        self.seeder = ProductStatusSeeder()

    def test_seeder_creates_all_statuses(self):
        self.seeder.run()
        names = set(
            ProductStatus.objects.values_list("name", flat=True)
        )
        expected = {"active", "inactive", "pending", "preorder"}
        self.assertEqual(names, expected)

    def test_seeder_creates_four_statuses(self):
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 4)

    def test_seeder_is_idempotent(self):
        self.seeder.run()
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 4)

    def test_seeder_preserves_existing_ids(self):
        status, _ = ProductStatus.objects.get_or_create(name="pending")
        original_id = status.pk
        self.seeder.run()
        status.refresh_from_db()
        self.assertEqual(status.pk, original_id)

    def test_seeder_normalizes_casing(self):
        ProductStatus.objects.create(name="ACTIVE")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 4)
        status = ProductStatus.objects.get(name="active")
        self.assertIsNotNone(status)

    def test_seeder_does_not_recreate_retired_statuses(self):
        """`wait_for_admin_confirmation` and `admin_rejected` are gone; the
        submissions table owns the review vocabulary now."""
        self.seeder.run()
        self.assertFalse(
            ProductStatus.objects.filter(
                name__in=["wait_for_admin_confirmation", "admin_rejected"]
            ).exists()
        )

    def test_seeder_keeps_preexisting_rows(self):
        ProductStatus.objects.get_or_create(name="pending")
        ProductStatus.objects.get_or_create(name="active")
        self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 4)

    def test_seeder_does_not_duplicate_on_multiple_runs(self):
        for _ in range(5):
            self.seeder.run()
        self.assertEqual(ProductStatus.objects.count(), 4)

    def test_seeder_statuses_are_lowercase(self):
        self.seeder.run()
        for status in ProductStatus.objects.all():
            self.assertEqual(status.name, status.name.lower())


class VendorProductStatusSeederTests(TestCase):
    """The review vocabulary is declared twice — once as the model's
    `Code`, once as the frozen list a migration can seed from — and these
    tests are what keeps the two from drifting apart."""

    def setUp(self):
        self.seeder = VendorProductStatusSeeder()

    def test_seeder_creates_exactly_the_model_vocabulary(self):
        self.seeder.run()
        self.assertEqual(
            set(VendorProductStatus.objects.values_list("name", flat=True)),
            set(VendorProductStatus.Code.values),
        )

    def test_seeder_is_idempotent(self):
        self.seeder.run()
        first = list(VendorProductStatus.objects.values_list("id", "name"))
        self.seeder.run()
        self.assertEqual(
            list(VendorProductStatus.objects.values_list("id", "name")), first
        )

    def test_the_review_queue_is_the_two_admin_states(self):
        self.seeder.run()
        pending = set(
            VendorProductStatus.objects.filter(
                name__in=[code.value for code in VendorProductStatus.PENDING_CODES]
            ).values_list("name", flat=True)
        )
        self.assertEqual(pending, {"confirmation_await", "request_update"})

    def test_a_draft_is_a_distinct_state(self):
        self.seeder.run()
        self.assertTrue(
            VendorProductStatus.objects.filter(name="draft").exists()
        )
