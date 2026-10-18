from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    VendorProduct,
    VendorProductStatus,
)
from domains.catalog.services.vendor_product_submission_service import (
    VendorProductSubmissionService,
)
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.services.vendor_product_service import VendorProductService


class VendorProductSecurityTests(TestCase):
    """Who may reach a submission, and what may still be done to it.

    The rules live in the service; these tests exercise them through the
    HTTP surface, because that is where "404 instead of 403" and the
    category scope guard actually have to hold.
    """

    def setUp(self):
        self.service = VendorProductSubmissionService()
        self.vendor_status, _ = VendorStatus.objects.get_or_create(
            id=VendorStatusEnum.ACTIVE.value,
            defaults={"name": "active", "title": "Active"},
        )
        self.vendor = Vendor.objects.create_user(
            phone="09121112233",
            password="pass1234",
            first_name="Test",
            last_name="Vendor",
            national_id="1234567890",
            status=self.vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09129998877",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="9876543210",
            status=self.vendor_status,
        )
        self.category_status, _ = CategoryStatus.objects.get_or_create(name="active")
        self.category, _ = Category.objects.get_or_create(
            name="Phones", defaults={"status": self.category_status}
        )
        self.out_of_scope, _ = Category.objects.get_or_create(
            name="Kitchen", defaults={"status": self.category_status}
        )
        self.active_status, _ = ProductStatus.objects.get_or_create(name="active")
        self.pending_status, _ = ProductStatus.objects.get_or_create(name="pending")

        # Each vendor trades in a different category, so "in scope" is a
        # meaningful distinction rather than a formality.
        self.business = BusinessProfile.objects.create(
            vendor=self.vendor,
            business_name="Vendor Business",
            display_name="Vendor",
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)
        self.other_business = BusinessProfile.objects.create(
            vendor=self.other_vendor,
            business_name="Other Business",
            display_name="Other",
        )
        BusinessCategory.objects.create(
            business=self.other_business, category=self.out_of_scope
        )

    def as_vendor(self, user=None):
        client = APIClient()
        client.force_authenticate(user=user or self.vendor)
        return client

    def make_draft(self, vendor=None):
        return self.service.create_submission(
            vendor=vendor or self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )

    def make_live_product(self, category=None):
        product = Product.objects.create(
            name="Live Phone", status=self.active_status
        )
        product.categories.add(category or self.category)
        return product

    # ── another vendor's submission is invisible ─────────────────────

    def test_another_vendors_submission_reports_missing_on_read(self):
        submission = self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().get(
            f"/api/vendor/product-submissions/{submission.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_another_vendors_submission_reports_missing_on_write(self):
        submission = self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().patch(
            f"/api/vendor/product-submissions/{submission.id}",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_another_vendors_submission_cannot_be_discarded(self):
        submission = self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().delete(
            f"/api/vendor/product-submissions/{submission.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_another_vendors_submission_cannot_be_sent_for_review(self):
        submission = self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().post(
            f"/api/vendor/product-submissions/{submission.id}/submit"
        )
        self.assertEqual(response.status_code, 404)

    def test_another_vendors_submission_cannot_take_files(self):
        submission = self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().get(
            f"/api/vendor/product-submissions/{submission.id}/files"
        )
        self.assertEqual(response.status_code, 404)

    def test_a_list_only_shows_your_own_submissions(self):
        self.make_draft()
        self.make_draft(vendor=self.other_vendor)
        response = self.as_vendor().get("/api/vendor/product-submissions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    # ── category scope ───────────────────────────────────────────────

    def test_a_draft_may_only_use_an_approved_category(self):
        response = self.as_vendor().post(
            "/api/vendor/product-submissions",
            {"name": "Kitchen Thing", "category_ids": [self.out_of_scope.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("category_ids", response.data["errors"])

    def test_a_revision_may_not_move_a_product_into_an_unapproved_category(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        response = self.as_vendor().patch(
            f"/api/vendor/product-submissions/{submission.id}",
            {"category_ids": [self.out_of_scope.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("category_ids", response.data["errors"])

    def test_an_out_of_scope_product_has_no_baseline_to_open(self):
        product = self.make_live_product(category=self.out_of_scope)
        response = self.as_vendor().post(
            "/api/vendor/product-submissions", {"product_id": product.id},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_a_vendor_without_a_profile_has_no_submission_scope(self):
        orphan = Vendor.objects.create_user(
            phone="09125556677",
            password="pass1234",
            first_name="Orphan",
            last_name="Vendor",
            national_id="1111222333",
            status=self.vendor_status,
        )
        response = self.as_vendor(orphan).post(
            "/api/vendor/product-submissions",
            {"name": "New Phone", "category_ids": [self.category.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    # ── a queued submission is frozen ────────────────────────────────

    def test_a_queued_submission_rejects_a_write(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        response = self.as_vendor().patch(
            f"/api/vendor/product-submissions/{submission.id}",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_a_queued_submission_cannot_be_discarded(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        response = self.as_vendor().delete(
            f"/api/vendor/product-submissions/{submission.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_media_writes_follow_the_same_gate(self):
        submission = self.make_draft()
        # Frozen: the admin would otherwise be reviewing media that moved.
        self.service.submit(submission, vendor=self.vendor)
        with self.assertRaises(PermissionDenied):
            self.service.require_editable(submission, self.vendor)
        with self.assertRaises(PermissionDenied):
            self.service.require_editable(submission, self.other_vendor)

        # Back from the admin, and it is the owner's again.
        self.service.decide(
            submission, code=VendorProductStatus.Code.NEED_RECHECK
        )
        self.service.require_editable(submission, self.vendor)
        with self.assertRaises(PermissionDenied):
            self.service.require_editable(submission, self.other_vendor)

    # ── admin review surface ─────────────────────────────────────────

    def test_a_vendor_cannot_reach_the_admin_queue(self):
        response = self.as_vendor().get("/api/catalog/vendor-products")
        self.assertEqual(response.status_code, 403)

    def test_a_vendor_cannot_confirm_a_submission(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        response = self.as_vendor().post(
            f"/api/catalog/vendor-products/{submission.id}/confirm", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        submission.refresh_from_db()
        self.assertIsNone(submission.product_id)

    # ── the catalog's own variant gate is unchanged ──────────────────

    def test_cannot_add_variant_while_pending(self):
        product = Product.objects.create(name="Pending", status=self.pending_status)
        product.categories.add(self.category)
        self.assertFalse(VendorProductService.can_manage_variants(product))

    def test_can_manage_variants_when_active(self):
        product = self.make_live_product()
        self.assertTrue(VendorProductService.can_manage_variants(product))
