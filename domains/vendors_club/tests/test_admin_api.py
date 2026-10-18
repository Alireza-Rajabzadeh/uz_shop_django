"""The admin panel's view of the vendor club.

Four things have to hold: every route needs a staff user holding the club
permission, an activity keeps its ``code`` forever, a membership can be rebuilt
from its ledger on demand, and a hand-entered movement obeys the same rules as
an automatic award — refused, not corrupted, when it would take a balance below
zero.
"""

from django.contrib.auth.models import Permission, User
from rest_framework.test import APITestCase

from domains.vendor.models import Vendor, VendorStatus

from ..models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)
from ..services import PointsService


BASE = "/api/vendors-club/admin"

CLUB_PERMISSIONS = (
    "view_vendorclubactivity",
    "add_vendorclubactivity",
    "change_vendorclubactivity",
    "view_vendorclubmembership",
    "change_vendorclubmembership",
    "view_vendorclubpointtransaction",
    "add_vendorclubpointtransaction",
)


def grant(user, *codenames):
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="vendors_club",
            codename__in=codenames,
        )
    )


class AdminClubApiFixture(APITestCase):
    def setUp(self):
        self.status, _ = VendorStatus.objects.get_or_create(
            id=1, defaults={"name": "active", "title": "Active"}
        )
        self.vendor = self.make_vendor(1, "Nima", "Seller")
        self.activity = VendorClubActivity.objects.create(
            code="profile.completed", name="Complete profile", points=100
        )
        self.admin = User.objects.create_user(
            username="club-admin", password="password", is_staff=True
        )
        grant(self.admin, *CLUB_PERMISSIONS)
        self.client.force_authenticate(self.admin)

    def make_vendor(self, index, first_name, last_name):
        return Vendor.objects.create_user(
            phone=f"091200009{index:02d}",
            password="pass1234",
            first_name=first_name,
            last_name=last_name,
            national_id=f"00000009{index:02d}",
            status=self.status,
        )

    def award(self, reference_id="1", vendor=None):
        return PointsService.award_points(
            vendor=vendor or self.vendor,
            activity_code=self.activity.code,
            reference_type="order",
            reference_id=reference_id,
        )

    def membership(self, vendor=None):
        return VendorClubMembership.objects.get(vendor=vendor or self.vendor)


class AdminClubAccessTests(AdminClubApiFixture):
    def test_the_routes_need_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(f"{BASE}/activities")

        self.assertIn(response.status_code, (401, 403))

    def test_a_staff_user_without_the_permission_is_denied(self):
        outsider = User.objects.create_user(
            username="outsider", password="password", is_staff=True
        )
        self.client.force_authenticate(outsider)

        response = self.client.get(f"{BASE}/activities")

        self.assertEqual(response.status_code, 403)


class AdminClubActivityTests(AdminClubApiFixture):
    def test_it_lists_and_filters_activities(self):
        VendorClubActivity.objects.create(
            code="order.delivered",
            name="Deliver an order",
            points=25,
            is_active=False,
        )

        listed = self.client.get(f"{BASE}/activities")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["data"]["count"], 2)

        active = self.client.get(f"{BASE}/activities?is_active=true")
        self.assertEqual(active.data["data"]["count"], 1)

        found = self.client.get(f"{BASE}/activities?search=deliver")
        self.assertEqual(found.data["data"]["count"], 1)
        self.assertEqual(
            found.data["data"]["results"][0]["code"], "order.delivered"
        )

    def test_it_creates_an_activity(self):
        response = self.client.post(
            f"{BASE}/activities",
            {"code": "first.sale", "name": "First sale", "points": 30},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["code"], "first.sale")
        self.assertTrue(response.data["data"]["is_active"])

    def test_it_rejects_a_non_positive_activity(self):
        response = self.client.post(
            f"{BASE}/activities",
            {"code": "free.points", "name": "Free", "points": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            VendorClubActivity.objects.filter(code="free.points").exists()
        )

    def test_it_rejects_a_duplicate_code(self):
        response = self.client.post(
            f"{BASE}/activities",
            {"code": self.activity.code, "name": "Duplicate", "points": 10},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_it_updates_the_editable_fields(self):
        response = self.client.patch(
            f"{BASE}/activities/{self.activity.id}",
            {"name": "Profile finished", "points": 120, "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.name, "Profile finished")
        self.assertEqual(self.activity.points, 120)
        self.assertFalse(self.activity.is_active)

    def test_the_code_cannot_be_changed(self):
        response = self.client.patch(
            f"{BASE}/activities/{self.activity.id}",
            {"code": "renamed.code", "name": "Still here"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.code, "profile.completed")

    def test_an_unknown_activity_is_a_404(self):
        response = self.client.get(f"{BASE}/activities/999999")

        self.assertEqual(response.status_code, 404)


class AdminClubMembershipTests(AdminClubApiFixture):
    def test_it_lists_memberships_with_balances(self):
        self.award()

        response = self.client.get(f"{BASE}/memberships")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(row["vendor_id"], self.vendor.id)
        self.assertEqual(row["vendor_code"], self.vendor.vendor_code)
        self.assertEqual(row["vendor_name"], "Nima Seller")
        self.assertEqual(row["lifetime_points"], 100)
        self.assertEqual(row["available_points"], 100)
        self.assertEqual(row["transaction_count"], 1)

    def test_it_searches_memberships_by_vendor_code(self):
        self.award()

        found = self.client.get(
            f"{BASE}/memberships?search={self.vendor.vendor_code}"
        )
        self.assertEqual(found.data["data"]["count"], 1)

        empty = self.client.get(f"{BASE}/memberships?search=NOPE")
        self.assertEqual(empty.data["data"]["count"], 0)

    def test_it_filters_memberships_by_points(self):
        self.award()
        idle = self.make_vendor(2, "Idle", "Seller")
        VendorClubMembership.objects.create(vendor=idle)

        with_points = self.client.get(f"{BASE}/memberships?has_points=true")
        self.assertEqual(with_points.data["data"]["count"], 1)
        self.assertEqual(
            with_points.data["data"]["results"][0]["vendor_id"], self.vendor.id
        )

        without = self.client.get(f"{BASE}/memberships?has_points=false")
        self.assertEqual(without.data["data"]["count"], 1)
        self.assertEqual(without.data["data"]["results"][0]["vendor_id"], idle.id)

    def test_the_detail_carries_the_recent_ledger(self):
        self.award()
        membership = self.membership()

        response = self.client.get(f"{BASE}/memberships/{membership.id}")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["transaction_count"], 1)
        self.assertEqual(len(data["recent_transactions"]), 1)
        row = data["recent_transactions"][0]
        self.assertEqual(row["transaction_type"], "earn")
        self.assertEqual(row["vendor_code"], self.vendor.vendor_code)

    def test_an_unknown_membership_is_a_404(self):
        response = self.client.get(f"{BASE}/memberships/999999")

        self.assertEqual(response.status_code, 404)


class AdminClubResyncTests(AdminClubApiFixture):
    def test_it_rebuilds_a_corrupted_cache(self):
        self.award()
        membership = self.membership()
        VendorClubMembership.objects.filter(pk=membership.pk).update(
            lifetime_points=999, available_points=999
        )

        response = self.client.post(
            f"{BASE}/memberships/{membership.id}/resync"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["repaired"])
        membership.refresh_from_db()
        self.assertEqual(membership.lifetime_points, 100)
        self.assertEqual(membership.available_points, 100)

    def test_a_balanced_membership_reports_no_repair(self):
        self.award()
        membership = self.membership()

        response = self.client.post(
            f"{BASE}/memberships/{membership.id}/resync"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["repaired"])

    def test_an_unknown_membership_is_a_404(self):
        response = self.client.post(f"{BASE}/memberships/999999/resync")

        self.assertEqual(response.status_code, 404)

    def test_it_needs_the_change_permission(self):
        self.award()
        membership = self.membership()
        viewer = User.objects.create_user(
            username="club-viewer", password="password", is_staff=True
        )
        grant(viewer, "view_vendorclubmembership")
        self.client.force_authenticate(viewer)

        response = self.client.post(
            f"{BASE}/memberships/{membership.id}/resync"
        )

        self.assertEqual(response.status_code, 403)


class AdminClubTransactionTests(AdminClubApiFixture):
    def test_it_lists_the_whole_ledger(self):
        self.award(reference_id="1")
        other = self.make_vendor(2, "Other", "Seller")
        self.award(vendor=other, reference_id="1")

        response = self.client.get(f"{BASE}/transactions")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["count"], 2)
        self.assertEqual(
            {row["vendor_id"] for row in data["results"]},
            {self.vendor.id, other.id},
        )
        self.assertEqual(data["results"][0]["vendor_code"], other.vendor_code)

    def test_it_filters_by_vendor_and_transaction_type(self):
        self.award(reference_id="1")
        PointsService.record_transaction(
            vendor=self.vendor,
            transaction_type="spend",
            points=30,
        )

        by_type = self.client.get(f"{BASE}/transactions?transaction_type=spend")
        self.assertEqual(by_type.data["data"]["count"], 1)
        self.assertEqual(
            by_type.data["data"]["results"][0]["transaction_type"], "spend"
        )

        by_vendor = self.client.get(
            f"{BASE}/transactions?vendor_id={self.vendor.id}"
        )
        self.assertEqual(by_vendor.data["data"]["count"], 2)

        missing = self.client.get(f"{BASE}/transactions?vendor_id=999999")
        self.assertEqual(missing.data["data"]["count"], 0)

    def test_it_searches_by_reference_and_vendor(self):
        self.award(reference_id="order-77")

        by_reference = self.client.get(f"{BASE}/transactions?search=order-77")
        self.assertEqual(by_reference.data["data"]["count"], 1)

        by_vendor = self.client.get(
            f"{BASE}/transactions?search={self.vendor.vendor_code}"
        )
        self.assertEqual(by_vendor.data["data"]["count"], 1)

    def test_a_date_range_that_ends_before_it_starts_is_rejected(self):
        response = self.client.get(
            f"{BASE}/transactions?created_from=2026-01-02&created_to=2026-01-01"
        )

        self.assertEqual(response.status_code, 400)

    def test_the_detail_carries_the_vendor(self):
        self.award()
        entry = VendorClubPointTransaction.objects.get()

        response = self.client.get(f"{BASE}/transactions/{entry.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["vendor_id"], self.vendor.id)

    def test_it_records_an_adjustment(self):
        self.award()

        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "adjustment",
                "points": 40,
                "description": "Goodwill",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(data["transaction_type"], "adjustment")
        self.assertEqual(data["vendor_code"], self.vendor.vendor_code)
        self.assertEqual(data["description"], "Goodwill")
        membership = self.membership()
        self.assertEqual(membership.lifetime_points, 100)
        self.assertEqual(membership.available_points, 140)

    def test_it_records_a_spend(self):
        self.award()

        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "spend",
                "points": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        membership = self.membership()
        self.assertEqual(membership.lifetime_points, 100)
        self.assertEqual(membership.available_points, 70)

    def test_it_refuses_a_spend_beyond_the_available_balance(self):
        self.award()

        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "spend",
                "points": 101,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        membership = self.membership()
        self.assertEqual(membership.available_points, 100)
        self.assertEqual(membership.transactions.count(), 1)

    def test_it_refuses_a_reversal_beyond_the_lifetime_balance(self):
        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "reversal",
                "points": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(VendorClubPointTransaction.objects.count(), 0)
        self.assertFalse(
            VendorClubMembership.objects.filter(vendor=self.vendor).exists()
        )

    def test_it_refuses_a_half_reference(self):
        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "adjustment",
                "points": 10,
                "reference_type": "order",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_it_refuses_an_unknown_vendor(self):
        response = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": 999999,
                "transaction_type": "adjustment",
                "points": 10,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_it_refuses_a_duplicate_identified_award(self):
        payload = {
            "vendor": self.vendor.id,
            "transaction_type": "earn",
            "points": 100,
            "activity": self.activity.id,
            "reference_type": "order",
            "reference_id": "order-1",
        }

        first = self.client.post(f"{BASE}/transactions", payload, format="json")
        second = self.client.post(f"{BASE}/transactions", payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            VendorClubPointTransaction.objects.filter(
                membership__vendor=self.vendor
            ).count(),
            1,
        )

    def test_it_needs_the_add_permission(self):
        viewer = User.objects.create_user(
            username="ledger-viewer", password="password", is_staff=True
        )
        grant(viewer, "view_vendorclubpointtransaction")
        self.client.force_authenticate(viewer)

        listed = self.client.get(f"{BASE}/transactions")
        created = self.client.post(
            f"{BASE}/transactions",
            {
                "vendor": self.vendor.id,
                "transaction_type": "adjustment",
                "points": 10,
            },
            format="json",
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(created.status_code, 403)


class AdminClubOverviewTests(AdminClubApiFixture):
    def test_it_reports_program_totals(self):
        self.award()
        PointsService.record_transaction(
            vendor=self.vendor,
            transaction_type="spend",
            points=30,
        )

        response = self.client.get(f"{BASE}/overview")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["members"], 1)
        self.assertEqual(data["lifetime_points"], 100)
        self.assertEqual(data["available_points"], 70)
        self.assertEqual(data["transaction_count"], 2)
        self.assertEqual(data["activities"], {"total": 1, "active": 1})
        self.assertEqual(data["totals_by_type"]["earn"], 100)
        self.assertEqual(data["totals_by_type"]["spend"], 30)
        self.assertEqual(data["totals_by_type"]["adjustment"], 0)
        self.assertEqual(data["totals_by_type"]["reversal"], 0)
        self.assertEqual(len(data["top_activities"]), 1)
        self.assertEqual(
            data["top_activities"][0]["code"], "profile.completed"
        )
        self.assertEqual(data["top_activities"][0]["total_points"], 100)

    def test_it_is_empty_on_a_fresh_club(self):
        response = self.client.get(f"{BASE}/overview")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["members"], 0)
        self.assertEqual(data["transaction_count"], 0)
        self.assertEqual(data["top_activities"], [])
