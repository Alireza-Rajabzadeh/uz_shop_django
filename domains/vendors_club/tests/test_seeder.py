from django.test import TestCase

from core.management.seeders.vendors_club import VendorsClubSeeder
from domains.vendors_club.data.activities import VENDOR_CLUB_ACTIVITY_SEED
from domains.vendors_club.data.transaction_types import (
    VENDOR_CLUB_TRANSACTION_TYPE_SEED,
)
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubPointTransaction,
    VendorClubPointTransactionType,
)


class VendorsClubActivitySeederTests(TestCase):
    def setUp(self):
        self.seeder = VendorsClubSeeder()

    def test_seeder_creates_the_predefined_activities(self):
        self.seeder.run()
        self.assertEqual(
            set(VendorClubActivity.objects.values_list("code", flat=True)),
            {row["code"] for row in VENDOR_CLUB_ACTIVITY_SEED},
        )

    def test_seeded_activities_are_active(self):
        self.seeder.run()
        self.assertFalse(
            VendorClubActivity.objects.filter(is_active=False).exists()
        )

    def test_seeder_does_not_revert_tuned_points(self):
        self.seeder.run()
        activity = VendorClubActivity.objects.get(code="profile.completed")
        activity.points = 777
        activity.save(update_fields=["points"])

        self.seeder.run()

        activity.refresh_from_db()
        self.assertEqual(activity.points, 777)


class VendorClubTransactionTypeSeederTests(TestCase):
    """The movement vocabulary is declared twice — as the ledger's
    `TransactionType` and as the reference rows — and these tests keep the two
    from drifting apart."""

    def setUp(self):
        self.seeder = VendorsClubSeeder()

    def test_the_migration_seeds_the_full_vocabulary(self):
        # 0002 seeds these rows, so a migrated database already has them.
        self.assertEqual(
            set(
                VendorClubPointTransactionType.objects.values_list(
                    "code", flat=True
                )
            ),
            set(VendorClubPointTransaction.TransactionType.values),
        )

    def test_the_seed_rows_match_the_ledger_choices(self):
        self.assertEqual(
            {row["code"] for row in VENDOR_CLUB_TRANSACTION_TYPE_SEED},
            set(VendorClubPointTransaction.TransactionType.values),
        )

    def test_seeder_restores_a_removed_row(self):
        VendorClubPointTransactionType.objects.filter(code="earn").delete()

        self.seeder.run()

        self.assertTrue(
            VendorClubPointTransactionType.objects.filter(code="earn").exists()
        )


class VendorsClubSeederIdempotencyTests(TestCase):
    def setUp(self):
        self.seeder = VendorsClubSeeder()

    def test_repeated_runs_never_duplicate(self):
        for _ in range(5):
            self.seeder.run()

        self.assertEqual(
            VendorClubActivity.objects.count(), len(VENDOR_CLUB_ACTIVITY_SEED)
        )
        self.assertEqual(
            VendorClubPointTransactionType.objects.count(),
            len(VENDOR_CLUB_TRANSACTION_TYPE_SEED),
        )

    def test_seeder_preserves_existing_ids(self):
        self.seeder.run()
        first = list(VendorClubActivity.objects.values_list("id", "code"))
        self.seeder.run()
        self.assertEqual(
            list(VendorClubActivity.objects.values_list("id", "code")), first
        )
