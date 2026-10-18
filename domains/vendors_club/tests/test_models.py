from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from domains.vendor.models import Vendor, VendorStatus
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)


class VendorClubTestCase(TestCase):
    def setUp(self):
        self.vendor_status = VendorStatus.objects.create(
            id=1,
            name="active",
            title="Active",
        )
        self.vendor = Vendor.objects.create_user(
            phone="09121112233",
            password="pass1234",
            first_name="Test",
            last_name="Vendor",
            national_id="1234567890",
            status=self.vendor_status,
        )
        self.membership = VendorClubMembership.objects.create(vendor=self.vendor)
        self.activity = VendorClubActivity.objects.create(
            code="profile.completed",
            name="Complete profile",
            points=100,
        )

    def earn(self, **overrides):
        payload = {
            "membership": self.membership,
            "activity": self.activity,
            "transaction_type": VendorClubPointTransaction.TransactionType.EARN,
            "points": 100,
            "reference_type": "order",
            "reference_id": "1",
        }
        payload.update(overrides)
        return VendorClubPointTransaction.objects.create(**payload)


class VendorClubActivityTests(VendorClubTestCase):
    def test_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VendorClubActivity.objects.create(
                    code="profile.completed", name="Duplicate", points=10
                )

    def test_points_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VendorClubActivity.objects.create(
                    code="zero.points", name="Zero", points=0
                )

    def test_code_cannot_change_after_creation(self):
        self.activity.code = "renamed"

        with self.assertRaises(ValidationError):
            self.activity.save()

        self.activity.refresh_from_db()
        self.assertEqual(self.activity.code, "profile.completed")

    def test_deleting_an_activity_with_history_is_protected(self):
        self.earn()

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.activity.delete()

        self.activity.refresh_from_db()


class VendorClubMembershipTests(VendorClubTestCase):
    def test_there_is_only_one_membership_per_vendor(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VendorClubMembership.objects.create(vendor=self.vendor)

    def test_balances_default_to_zero(self):
        self.assertEqual(self.membership.lifetime_points, 0)
        self.assertEqual(self.membership.available_points, 0)
        self.assertIsNone(self.membership.last_synced_at)

    def test_deleting_a_membership_with_history_is_protected(self):
        self.earn()

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.membership.delete()

        self.membership.refresh_from_db()


class VendorClubPointTransactionTests(VendorClubTestCase):
    def test_points_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.earn(points=0)

    def test_a_duplicate_earn_for_the_same_source_is_rejected_by_the_database(self):
        self.earn()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.earn()

    def test_the_same_source_may_earn_under_a_different_activity(self):
        other = VendorClubActivity.objects.create(
            code="first.order", name="First order", points=50
        )
        self.earn()
        self.earn(activity=other)

        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)

    def test_a_duplicate_earn_for_another_membership_is_allowed(self):
        other_vendor = Vendor.objects.create_user(
            phone="09121112244",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="0987654321",
            status=self.vendor_status,
        )
        other_membership = VendorClubMembership.objects.create(vendor=other_vendor)
        self.earn()
        self.earn(membership=other_membership)

        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)

    def test_an_earn_without_a_reference_may_repeat(self):
        self.earn(reference_type=None, reference_id=None)
        self.earn(reference_type=None, reference_id=None)

        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)

    def test_a_spend_does_not_collide_with_the_earn_for_the_same_source(self):
        self.earn()
        self.earn(
            transaction_type=VendorClubPointTransaction.TransactionType.SPEND,
            points=30,
        )

        self.assertEqual(VendorClubPointTransaction.objects.count(), 2)

    def test_a_reference_must_be_a_type_and_id_pair(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.earn(reference_id=None)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.earn(reference_type=None)

    def test_an_existing_transaction_cannot_be_saved_again(self):
        entry = self.earn()
        entry.description = "edited"

        with self.assertRaises(ValidationError):
            entry.save()

        entry.refresh_from_db()
        self.assertEqual(entry.description, "")

    def test_an_instance_cannot_be_deleted(self):
        entry = self.earn()

        with self.assertRaises(ValidationError):
            entry.delete()

        self.assertEqual(VendorClubPointTransaction.objects.count(), 1)

    def test_bulk_update_is_refused(self):
        self.earn()

        with self.assertRaises(ValidationError):
            VendorClubPointTransaction.objects.all().update(description="edited")

        self.assertEqual(
            VendorClubPointTransaction.objects.get().description, ""
        )

    def test_bulk_delete_is_refused(self):
        self.earn()

        with self.assertRaises(ValidationError):
            VendorClubPointTransaction.objects.all().delete()

        self.assertEqual(VendorClubPointTransaction.objects.count(), 1)

    def test_transactions_are_returned_chronologically(self):
        first = self.earn(reference_id="1")
        second = self.earn(reference_id="2")

        self.assertEqual(
            list(VendorClubPointTransaction.objects.all()),
            [first, second],
        )
