from datetime import timedelta
from threading import Barrier, Thread

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from domains.vendor.models import Vendor, VendorStatus
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)
from domains.vendors_club.services import AwardStatus, PointsService


def make_vendor(phone="09121112233", national_id="1234567890"):
    status, _ = VendorStatus.objects.get_or_create(
        id=1, defaults={"name": "active", "title": "Active"}
    )
    return Vendor.objects.create_user(
        phone=phone,
        password="pass1234",
        first_name="Test",
        last_name="Vendor",
        national_id=national_id,
        status=status,
    )


class PointsServiceTestCase(TestCase):
    def setUp(self):
        self.vendor = make_vendor()
        self.activity = VendorClubActivity.objects.create(
            code="profile.completed",
            name="Complete profile",
            points=100,
        )

    def award(self, **overrides):
        payload = {
            "vendor": self.vendor,
            "activity_code": self.activity.code,
            "reference_type": "order",
            "reference_id": "1",
        }
        payload.update(overrides)
        return PointsService.award_points(**payload)


class AwardPointsTests(PointsServiceTestCase):
    def test_an_award_creates_the_membership_and_moves_both_balances(self):
        result = self.award()

        self.assertTrue(result.awarded)
        self.assertEqual(result.status, AwardStatus.AWARDED)
        self.assertEqual(result.points, 100)
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(membership.available_points, 100)
        self.assertEqual(membership.lifetime_points, 100)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 1)

    def test_an_award_does_not_stamp_last_synced_at(self):
        result = self.award()

        # Incremental updates are not a reconciliation, so the sync clock is
        # left alone.
        self.assertIsNone(result.membership.last_synced_at)

    def test_an_unknown_activity_awards_nothing(self):
        result = PointsService.award_points(
            vendor=self.vendor,
            activity_code="does.not.exist",
            reference_type="order",
            reference_id="1",
        )

        self.assertEqual(result.status, AwardStatus.NOT_FOUND)
        self.assertFalse(result.awarded)
        self.assertFalse(VendorClubPointTransaction.objects.exists())
        # Not eligible: no membership is created either.
        self.assertFalse(VendorClubMembership.objects.filter(vendor=self.vendor).exists())

    def test_an_inactive_activity_awards_nothing(self):
        self.activity.is_active = False
        self.activity.save(update_fields=["is_active"])

        result = self.award()

        self.assertEqual(result.status, AwardStatus.INACTIVE)
        self.assertFalse(result.awarded)
        self.assertFalse(VendorClubPointTransaction.objects.exists())

    def test_a_duplicate_award_is_ignored(self):
        first = self.award()
        second = self.award()

        self.assertTrue(first.awarded)
        self.assertEqual(second.status, AwardStatus.DUPLICATE)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 1)
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(membership.available_points, 100)

    def test_a_new_source_reference_awards_again(self):
        self.award(reference_id="1")
        result = self.award(reference_id="2")

        self.assertTrue(result.awarded)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(membership.available_points, 200)

    def test_an_award_without_a_reference_is_not_deduplicated(self):
        self.award(reference_type=None, reference_id=None)
        result = self.award(reference_type=None, reference_id=None)

        self.assertTrue(result.awarded)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)


class GetMembershipTests(PointsServiceTestCase):
    def test_get_membership_creates_the_membership_on_first_use(self):
        membership = PointsService.get_membership(self.vendor)

        self.assertEqual(membership.vendor_id, self.vendor.id)
        self.assertEqual(membership.available_points, 0)
        self.assertEqual(membership.lifetime_points, 0)
        # A never-synced membership reconciles once, so the clock is set.
        self.assertIsNotNone(membership.last_synced_at)

    def test_get_membership_reconciles_a_never_synced_membership(self):
        self.award()
        VendorClubMembership.objects.filter(vendor=self.vendor).update(
            available_points=7, lifetime_points=7
        )

        membership = PointsService.get_membership(self.vendor)

        self.assertEqual(membership.available_points, 100)
        self.assertEqual(membership.lifetime_points, 100)

    def test_get_membership_trusts_stored_balances_before_the_interval(self):
        self.award()
        # A fresh timestamp plus deliberately wrong balances: if a full
        # rebuild ran, the wrong values would be corrected.
        VendorClubMembership.objects.filter(vendor=self.vendor).update(
            last_synced_at=timezone.now(),
            available_points=7,
            lifetime_points=7,
        )

        membership = PointsService.get_membership(self.vendor)

        self.assertEqual(membership.available_points, 7)
        self.assertEqual(membership.lifetime_points, 7)

    @override_settings(VENDORS_CLUB_SYNC_INTERVAL_SECONDS=5)
    def test_get_membership_reconciles_once_the_interval_elapses(self):
        self.award()
        VendorClubMembership.objects.filter(vendor=self.vendor).update(
            last_synced_at=timezone.now() - timedelta(seconds=10),
            available_points=7,
            lifetime_points=7,
        )

        membership = PointsService.get_membership(self.vendor)

        self.assertEqual(membership.available_points, 100)

    def test_force_sync_rebuilds_even_when_not_due(self):
        self.award()
        VendorClubMembership.objects.filter(vendor=self.vendor).update(
            last_synced_at=timezone.now(),
            available_points=7,
            lifetime_points=7,
        )

        membership = PointsService.get_membership(self.vendor, force_sync=True)

        self.assertEqual(membership.available_points, 100)


class SyncPointsTests(PointsServiceTestCase):
    def test_sync_repairs_one_membership_and_stamps_the_clock(self):
        self.award()
        VendorClubMembership.objects.filter(vendor=self.vendor).update(
            available_points=7, lifetime_points=7
        )

        result = PointsService.sync_points(VendorClubMembership.objects.get(vendor=self.vendor))

        self.assertTrue(result.repaired)
        self.assertEqual(result.available_points, 100)
        self.assertEqual(result.lifetime_points, 100)
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(membership.available_points, 100)
        self.assertIsNotNone(membership.last_synced_at)

    def test_sync_reports_no_repair_when_balances_already_match(self):
        self.award()

        result = PointsService.sync_points(VendorClubMembership.objects.get(vendor=self.vendor))

        self.assertFalse(result.repaired)

    def test_sync_without_an_argument_reconciles_every_membership(self):
        self.award()
        other_vendor = make_vendor(phone="09121112244", national_id="0987654321")
        other_activity = VendorClubActivity.objects.create(
            code="first.login", name="First login", points=25
        )
        PointsService.award_points(
            vendor=other_vendor,
            activity_code=other_activity.code,
            reference_type="session",
            reference_id="1",
        )
        VendorClubMembership.objects.update(available_points=0, lifetime_points=0)

        results = PointsService.sync_points()

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.repaired for result in results))

    def test_reconciliation_applies_the_direction_rules(self):
        self.award()
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        VendorClubPointTransaction.objects.create(
            membership=membership,
            activity=self.activity,
            transaction_type=VendorClubPointTransaction.TransactionType.SPEND,
            points=30,
            reference_type="order",
            reference_id="spend-1",
        )
        VendorClubPointTransaction.objects.create(
            membership=membership,
            activity=None,
            transaction_type=VendorClubPointTransaction.TransactionType.REVERSAL,
            points=10,
            reference_type="point_transaction",
            reference_id="1",
        )

        result = PointsService.sync_points(membership)

        # earn 100 (+/+), spend 30 (0/-), reversal 10 (-/-)
        self.assertEqual(result.lifetime_points, 90)
        self.assertEqual(result.available_points, 60)

    @override_settings(VENDORS_CLUB_SYNC_INTERVAL_SECONDS=5)
    def test_due_memberships_covers_stale_and_never_synced(self):
        fresh = VendorClubMembership.objects.create(vendor=self.vendor)
        VendorClubMembership.objects.filter(pk=fresh.pk).update(
            last_synced_at=timezone.now()
        )
        stale_vendor = make_vendor(phone="09121112255", national_id="1111111111")
        stale = VendorClubMembership.objects.create(vendor=stale_vendor)
        VendorClubMembership.objects.filter(pk=stale.pk).update(
            last_synced_at=timezone.now() - timedelta(seconds=10)
        )
        never_vendor = make_vendor(phone="09121112266", national_id="2222222222")
        never = VendorClubMembership.objects.create(vendor=never_vendor)

        due = set(PointsService.due_memberships().values_list("id", flat=True))

        self.assertNotIn(fresh.pk, due)
        self.assertIn(stale.pk, due)
        self.assertIn(never.pk, due)


class ConcurrentAwardTests(TransactionTestCase):
    """`select_for_update` plus `F()` updates must not lose a balance."""

    def setUp(self):
        self.vendor = make_vendor()
        self.activity = VendorClubActivity.objects.create(
            code="profile.completed",
            name="Complete profile",
            points=100,
        )
        VendorClubMembership.objects.create(vendor=self.vendor)

    def run_concurrently(self, targets):
        barrier = Barrier(len(targets))
        errors = []

        def worker(target):
            try:
                barrier.wait(timeout=10)
                target()
            except Exception as exc:  # pragma: no cover - re-raised below
                errors.append(exc)
            finally:
                connection.close()

        threads = [Thread(target=worker, args=(target,)) for target in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return errors

    def test_concurrent_awards_accumulate_every_point(self):
        errors = self.run_concurrently(
            [
                lambda reference_id=reference_id: PointsService.award_points(
                    vendor=self.vendor,
                    activity_code=self.activity.code,
                    reference_type="order",
                    reference_id=reference_id,
                )
                for reference_id in ("1", "2")
            ]
        )

        self.assertEqual(errors, [])
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)
        self.assertEqual(membership.available_points, 200)
        self.assertEqual(membership.lifetime_points, 200)

    def test_concurrent_awards_of_one_source_award_once(self):
        errors = self.run_concurrently(
            [
                lambda: PointsService.award_points(
                    vendor=self.vendor,
                    activity_code=self.activity.code,
                    reference_type="order",
                    reference_id="1",
                )
                for _ in range(2)
            ]
        )

        self.assertEqual(errors, [])
        membership = VendorClubMembership.objects.get(vendor=self.vendor)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 1)
        self.assertEqual(membership.available_points, 100)
