from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
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


class VendorProductSubmissionLifecycleTests(TestCase):
    """The review vocabulary, from a vendor's first draft to a live product.

    The catalog keeps a product's lifecycle in `ProductStatus`; this suite is
    about the *submission* vocabulary that sits in front of it.
    """

    def setUp(self):
        self.service = VendorProductSubmissionService()
        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
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
        self.other_vendor = Vendor.objects.create_user(
            phone="09121112244",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="0987654321",
            status=self.vendor_status,
        )
        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Phones", status=self.category_status
        )
        self.second_category = Category.objects.create(
            name="Tablets", status=self.category_status
        )
        self.pending_status, _ = ProductStatus.objects.get_or_create(name="pending")
        self.active_status, _ = ProductStatus.objects.get_or_create(name="active")
        self.admin = User.objects.create_superuser(
            username="admin", password="password"
        )

    # ── helpers ──────────────────────────────────────────────────────

    def code(self, submission):
        submission.refresh_from_db()
        return submission.status.name

    def make_draft(self):
        return self.service.create_submission(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
            description="a phone",
        )

    def make_live_product(self, **overrides):
        product = Product.objects.create(
            name=overrides.get("name", "Live Phone"),
            status=self.active_status,
            description=overrides.get("description", "live description"),
        )
        product.categories.add(
            *overrides.get("categories", [self.category])
        )
        return product

    # ── first-time drafts ────────────────────────────────────────────

    def test_new_submission_starts_as_a_draft(self):
        submission = self.make_draft()
        self.assertEqual(self.code(submission), "draft")
        self.assertIsNone(submission.product_id)
        self.assertTrue(self.service.is_editable(submission))
        self.assertFalse(self.service.is_pending(submission))

    def test_editing_a_draft_keeps_it_a_draft(self):
        submission = self.make_draft()
        self.service.update_submission(
            submission, vendor=self.vendor, name="Renamed", description="new copy"
        )
        self.assertEqual(self.code(submission), "draft")
        self.assertEqual(submission.name, "Renamed")
        self.assertEqual(submission.description, "new copy")

    def test_submit_moves_a_draft_into_the_queue(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.assertEqual(self.code(submission), "confirmation_await")
        self.assertTrue(self.service.is_pending(submission))

    def test_a_queued_draft_is_frozen(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        with self.assertRaises(PermissionDenied):
            self.service.update_submission(
                submission, vendor=self.vendor, name="Should Fail"
            )
        with self.assertRaises(PermissionDenied):
            self.service.submit(submission, vendor=self.vendor)

    def test_only_the_owner_can_touch_a_submission(self):
        submission = self.make_draft()
        with self.assertRaises(PermissionDenied):
            self.service.update_submission(
                submission, vendor=self.other_vendor, name="Should Fail"
            )
        with self.assertRaises(PermissionDenied):
            self.service.submit(submission, vendor=self.other_vendor)

    def test_a_name_is_required_to_open_a_draft(self):
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.create_submission(
                vendor=self.vendor, name="   ", category_ids=[self.category.id]
            )

    def test_categories_are_required_to_open_a_draft(self):
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.create_submission(
                vendor=self.vendor, name="New Phone", category_ids=[]
            )

    def test_discard_throws_away_a_first_draft(self):
        submission = self.make_draft()
        self.assertIsNone(
            self.service.discard(submission, vendor=self.vendor)
        )
        self.assertFalse(VendorProduct.objects.filter(pk=submission.pk).exists())

    # ── confirm: draft → live product ────────────────────────────────

    def test_confirm_creates_an_active_catalog_product(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.confirm(submission, admin=self.admin, response="ok")

        submission.refresh_from_db()
        product = submission.product
        self.assertIsNotNone(product)
        self.assertEqual(self.code(submission), "confirmed")
        self.assertEqual(product.name, "New Phone")
        self.assertEqual(product.description, "a phone")
        self.assertEqual(product.status.name, "active")
        self.assertEqual(product.creator_model, "vendor.vendor")
        self.assertEqual(product.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(
            list(product.categories.values_list("id", flat=True)),
            [self.category.id],
        )

    def test_confirm_records_the_admin_who_approved_it(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.confirm(submission, admin=self.admin, response="looks fine")
        submission.refresh_from_db()
        self.assertEqual(submission.confirmed_by_id, self.admin.pk)
        self.assertIsNotNone(submission.confirmed_at)
        self.assertEqual(submission.admin_response, "looks fine")

    def test_confirm_requires_something_awaiting_confirmation(self):
        submission = self.make_draft()
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.confirm(submission, admin=self.admin)

    def test_a_confirmed_submission_cannot_be_confirmed_twice(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.confirm(submission, admin=self.admin)
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.confirm(submission, admin=self.admin)

    # ── baseline: staging edits to a live product ────────────────────

    def test_baseline_copies_the_live_product(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.assertEqual(submission.product_id, product.pk)
        self.assertEqual(self.code(submission), "draft")
        self.assertEqual(submission.name, product.name)
        self.assertEqual(submission.description, product.description)
        self.assertEqual(
            set(submission.categories.values_list("id", flat=True)),
            set(product.categories.values_list("id", flat=True)),
        )
        self.assertEqual(self.service.changed_fields(submission), set())

    def test_baseline_is_returned_to_the_same_vendor(self):
        product = self.make_live_product()
        first = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        second = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.assertEqual(first.pk, second.pk)

    def test_another_vendor_cannot_open_a_second_submission(self):
        product = self.make_live_product()
        self.service.create_or_get_baseline(vendor=self.vendor, product=product)
        with self.assertRaises(PermissionDenied):
            self.service.create_or_get_baseline(
                vendor=self.other_vendor, product=product
            )

    # ── revisions: draft → request_update → applied ──────────────────

    def test_editing_a_live_submission_reports_what_changed(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name",
            description="better copy",
        )
        self.assertEqual(
            self.service.changed_fields(submission), {"name", "description"}
        )

    def test_sending_a_revision_back_puts_the_vendor_in_the_queue(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name"
        )
        self.service.submit(submission, vendor=self.vendor)
        self.assertEqual(self.code(submission), "request_update")
        with self.assertRaises(PermissionDenied):
            self.service.update_submission(
                submission, vendor=self.vendor, name="Should Fail"
            )

    def test_sending_an_unchanged_revision_is_refused(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.submit(submission, vendor=self.vendor)
        self.assertEqual(self.code(submission), "draft")

    def test_apply_copies_only_the_fields_the_admin_selected(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name",
            description="better copy",
        )
        self.service.submit(submission, vendor=self.vendor)

        self.service.apply(
            submission, admin=self.admin, fields=["name"], response="name ok"
        )
        product.refresh_from_db()
        submission.refresh_from_db()

        # The selected field reaches the catalog.
        self.assertEqual(product.name, "Better Name")
        # The unselected one does not.
        self.assertEqual(product.description, "live description")
        # And the staged copy is reverted, so `confirmed` stays true.
        self.assertEqual(submission.name, product.name)
        self.assertEqual(submission.description, product.description)
        self.assertEqual(self.code(submission), "confirmed")
        self.assertEqual(self.service.changed_fields(submission), set())
        self.assertEqual(submission.confirmed_by_id, self.admin.pk)

    def test_apply_refuses_a_submission_that_is_not_queued(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name"
        )
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.apply(submission, admin=self.admin, fields=["name"])

    def test_apply_refuses_an_unknown_field(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name"
        )
        self.service.submit(submission, vendor=self.vendor)
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.apply(
                submission, admin=self.admin, fields=["name", "price"]
            )

    # ── sending work back to the vendor ──────────────────────────────

    def test_decide_sends_a_submission_back_with_a_note(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.decide(
            submission,
            code=VendorProductStatus.Code.NEED_RECHECK,
            response="add a brand",
        )
        self.assertEqual(self.code(submission), "need_recheck")
        self.assertEqual(submission.admin_response, "add a brand")
        # Nothing reached the catalog.
        self.assertIsNone(submission.product_id)
        # And the vendor can act on it again.
        self.assertTrue(self.service.is_editable(submission))

    def test_decide_can_reject_outright(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.decide(
            submission, code=VendorProductStatus.Code.REJECT,
            response="out of scope",
        )
        self.assertEqual(self.code(submission), "reject")
        self.assertIsNone(submission.product_id)

    def test_decide_refuses_a_submission_that_has_been_decided(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        self.service.decide(submission, code=VendorProductStatus.Code.NEED_RECHECK)
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.decide(
                submission, code=VendorProductStatus.Code.NEED_RECHECK
            )

    def test_decide_refuses_to_confirm_silently(self):
        submission = self.make_draft()
        self.service.submit(submission, vendor=self.vendor)
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.service.decide(submission, code="confirmed")

    def test_a_returned_submission_can_be_fixed_and_resent(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name"
        )
        self.service.submit(submission, vendor=self.vendor)
        self.service.decide(
            submission, code=VendorProductStatus.Code.NEED_RECHECK,
            response="not good enough",
        )

        self.assertTrue(self.service.is_editable(submission))
        self.service.update_submission(
            submission, vendor=self.vendor, name="Good Name"
        )
        self.assertEqual(self.code(submission), "need_recheck")
        self.service.submit(submission, vendor=self.vendor)
        self.assertEqual(self.code(submission), "request_update")

    def test_discard_reverts_a_live_submission_to_the_catalog(self):
        product = self.make_live_product()
        submission = self.service.create_or_get_baseline(
            vendor=self.vendor, product=product
        )
        self.service.update_submission(
            submission, vendor=self.vendor, name="Better Name"
        )
        self.service.discard(submission, vendor=self.vendor)
        submission.refresh_from_db()
        self.assertEqual(submission.name, product.name)
        self.assertEqual(self.code(submission), "confirmed")
        self.assertEqual(self.service.changed_fields(submission), set())
        self.assertIsNone(submission.admin_response)


class VendorProductSubmissionDetailTests(TestCase):
    """The `details` payload is resolved by the catalog's own rule.

    The API sends `{"detail_id", "value"}` pairs; the service must map them to
    the definitions the selected categories actually expose, and must refuse
    ids that belong to another category or repeat within one payload.
    """

    def setUp(self):
        self.service = VendorProductSubmissionService()
        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value,
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
        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Phones", status=self.category_status
        )
        self.other_category = Category.objects.create(
            name="Tablets", status=self.category_status
        )

        self.network = CategoryDetail.objects.create(name="Network", type="text")
        CategoryDetailRelation.objects.create(
            category=self.category, detail=self.network, value=""
        )
        self.ram = CategoryDetail.objects.create(name="RAM", type="text")
        CategoryDetailRelation.objects.create(
            category=self.other_category, detail=self.ram, value=""
        )

    def make_draft(self, **data):
        payload = {
            "vendor": self.vendor,
            "name": "New Phone",
            "category_ids": [self.category.id],
        }
        payload.update(data)
        return self.service.create_submission(**payload)

    def test_details_resolve_to_their_definition(self):
        submission = self.make_draft(
            details=[{"detail_id": self.network.id, "value": "5G"}]
        )
        row = submission.details.get()
        self.assertEqual(row.detail_id, self.network.id)
        self.assertEqual(row.value, "5G")

    def test_a_detail_from_another_category_is_rejected(self):
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.make_draft(details=[{"detail_id": self.ram.id, "value": "8"}])

    def test_duplicate_details_are_rejected(self):
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.make_draft(
                details=[
                    {"detail_id": self.network.id, "value": "5G"},
                    {"detail_id": self.network.id, "value": "4G"},
                ]
            )

    def test_an_unknown_detail_id_is_rejected(self):
        with self.assertRaises(VendorProductSubmissionService.ValidationError):
            self.make_draft(details=[{"detail_id": 999999, "value": "x"}])

    def test_update_replaces_the_detail_rows(self):
        submission = self.make_draft(
            details=[{"detail_id": self.network.id, "value": "5G"}]
        )
        self.service.update_submission(
            submission,
            vendor=self.vendor,
            details=[{"detail_id": self.network.id, "value": "LTE"}],
        )
        self.assertEqual(submission.details.count(), 1)
        self.assertEqual(submission.details.get().value, "LTE")


class VendorProductStatusModelTests(TestCase):
    def test_pending_codes_are_only_the_two_admin_states(self):
        self.assertEqual(
            VendorProductStatus.PENDING_CODES,
            {
                VendorProductStatus.Code.CONFIRMATION_AWAIT,
                VendorProductStatus.Code.REQUEST_UPDATE,
            },
        )

    def test_the_draft_state_is_editable(self):
        service = VendorProductSubmissionService()
        self.assertIn(VendorProductStatus.Code.DRAFT, service.EDITABLE_CODES)
        self.assertNotIn(
            VendorProductStatus.Code.CONFIRMATION_AWAIT, service.EDITABLE_CODES
        )
        self.assertNotIn(
            VendorProductStatus.Code.REQUEST_UPDATE, service.EDITABLE_CODES
        )

    def test_every_code_has_a_status_row(self):
        self.assertEqual(
            sorted(VendorProductStatus.Code.values),
            sorted(VendorProductStatus.objects.values_list("name", flat=True)),
        )


class AdminProductStatusTests(TestCase):
    """The catalog's own product statuses still behave as before."""

    def setUp(self):
        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Phones", status=self.category_status
        )
        self.pending_status, _ = ProductStatus.objects.get_or_create(name="pending")
        self.active_status, _ = ProductStatus.objects.get_or_create(name="active")

    def test_admin_can_change_status_via_patch(self):
        product = Product.objects.create(name="Admin Product", status=self.pending_status)
        product.categories.add(self.category)

        admin = User.objects.create_superuser(username="admin", password="password")
        client = APIClient()
        client.force_authenticate(admin)

        response = client.patch(
            f"/api/catalog/products/{product.id}",
            {"status": self.active_status.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.status.name, "active")

    def test_existing_admin_create_flow_sets_pending(self):
        admin = User.objects.create_superuser(username="admin", password="password")
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(
            "/api/catalog/products",
            {
                "name": "Admin Phone",
                "status": self.pending_status.id,
                "category_ids": [self.category.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name="Admin Phone")
        self.assertEqual(product.status.name, "pending")

    def test_cannot_delete_active_status_when_products_exist(self):
        Product.objects.create(name="Active Product", status=self.active_status)
        status = ProductStatus.objects.get(name="active")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            status.delete()

    def test_cannot_delete_pending_status_when_products_exist(self):
        Product.objects.create(name="Pending Product", status=self.pending_status)
        status = ProductStatus.objects.get(name="pending")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            status.delete()
