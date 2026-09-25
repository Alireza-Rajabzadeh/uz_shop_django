from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus, ProductVariants
from domains.marketplace.models import BusinessOffer
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.services.vendor_product_service import VendorProductService


class VendorProductServiceTests(TestCase):
    def setUp(self):
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
            phone="09129998877",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="9876543210",
            status=self.vendor_status,
        )
        self.category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Phones", status=self.category_status
        )
        self.pending_status, _ = ProductStatus.objects.get_or_create(
            name="pending"
        )
        self.active_status, _ = ProductStatus.objects.get_or_create(
            name="active"
        )
        self.wait_status, _ = ProductStatus.objects.get_or_create(
            name="wait_for_admin_confirmation"
        )
        self.rejected_status, _ = ProductStatus.objects.get_or_create(
            name="admin_rejected"
        )
        self.inactive_status, _ = ProductStatus.objects.get_or_create(
            name="inactive"
        )

    def _make_product(self, status=None, vendor=None, creator_model=""):
        if status is None:
            status = self.pending_status
        product = Product.objects.create(
            name="Test Product", status=status
        )
        product.categories.add(self.category)
        if vendor:
            product.created_by_vendor = vendor
            product.creator_model = creator_model
            product.save(update_fields=["created_by_vendor", "creator_model"])
        return product

    # ─────────────────────── create_vendor_product ───────────────────────

    def test_create_vendor_product_sets_wait_for_admin_confirmation(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

    def test_create_vendor_product_sets_created_by_vendor(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(product.creator_model, "vendor.vendor")

    def test_create_vendor_product_sets_pending_status_initially_then_overrides(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertNotEqual(product.status.name, "pending")
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

    def test_create_vendor_product_with_description(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
            description="A great phone",
        )
        product.refresh_from_db()
        self.assertEqual(product.description, "A great phone")

    # ─────────────────────── update_vendor_product ───────────────────────

    def test_update_from_wait_for_admin_confirmation_resets_to_wait(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        VendorProductService.update_vendor_product(
            product, self.vendor, name="Updated Name",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.name, "Updated Name")

    def test_update_from_admin_rejected_resubmits_to_wait(self):
        product = self._make_product(
            status=self.rejected_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        VendorProductService.update_vendor_product(
            product, self.vendor, name="Resubmitted",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.name, "Resubmitted")

    def test_update_blocks_when_status_active(self):
        product = self._make_product(
            status=self.active_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_update_blocks_when_status_pending(self):
        product = self._make_product(
            status=self.pending_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_update_blocks_when_status_inactive(self):
        product = self._make_product(
            status=self.inactive_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_update_blocks_when_created_by_other_vendor(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.other_vendor, creator_model="vendor.vendor"
        )
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_update_blocks_when_creator_model_not_vendor(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="catalog.product"
        )
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    # ─────────────────────── can_vendor_edit ───────────────────────

    def test_can_edit_true_when_wait_for_admin_confirmation(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertTrue(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_true_when_admin_rejected(self):
        product = self._make_product(
            status=self.rejected_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertTrue(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_false_when_active(self):
        product = self._make_product(
            status=self.active_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertFalse(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_false_when_pending(self):
        product = self._make_product(
            status=self.pending_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertFalse(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_false_when_different_vendor(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.other_vendor, creator_model="vendor.vendor"
        )
        self.assertFalse(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_false_when_creator_model_not_vendor(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="catalog.product"
        )
        self.assertFalse(VendorProductService.can_vendor_edit(product, self.vendor))

    def test_can_edit_false_when_no_vendor(self):
        product = self._make_product(status=self.wait_status)
        self.assertFalse(VendorProductService.can_vendor_edit(product, self.vendor))

    # ─────────────────────── can_add_variant ───────────────────────

    def test_cannot_add_variant_when_wait_for_admin_confirmation(self):
        product = self._make_product(status=self.wait_status)
        self.assertFalse(VendorProductService.can_add_variant(product))

    def test_cannot_add_variant_when_admin_rejected(self):
        product = self._make_product(status=self.rejected_status)
        self.assertFalse(VendorProductService.can_add_variant(product))

    def test_can_add_variant_when_active(self):
        product = self._make_product(status=self.active_status)
        self.assertTrue(VendorProductService.can_add_variant(product))

    def test_can_add_variant_when_pending(self):
        product = self._make_product(status=self.pending_status)
        self.assertTrue(VendorProductService.can_add_variant(product))

    def test_can_add_variant_when_inactive(self):
        product = self._make_product(status=self.inactive_status)
        self.assertTrue(VendorProductService.can_add_variant(product))

    # ─────────────────────── find_similar_products ───────────────────────

    def test_find_similar_products_exact_match(self):
        Product.objects.create(name="Samsung Galaxy", status=self.active_status)
        results = VendorProductService.find_similar_products("Samsung Galaxy")
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["exact"])

    def test_find_similar_products_fuzzy_match(self):
        Product.objects.create(name="Samsung Galaxy S24", status=self.active_status)
        results = VendorProductService.find_similar_products("Samsung Galaxy S23")
        self.assertGreaterEqual(len(results), 1)

    def test_find_similar_products_no_match(self):
        Product.objects.create(name="Apple iPhone", status=self.active_status)
        results = VendorProductService.find_similar_products("Completely Different XYZ")
        self.assertEqual(len(results), 0)

    def test_vendor_variant_patch_creates_business_offer_for_price_and_discount(self):
        business = BusinessProfile.objects.create(
            id=9999,
            vendor=self.vendor,
            business_name="Test Business",
            display_name="Test Business",
        )
        BusinessCategory.objects.create(business=business, category=self.category)
        product = Product.objects.create(name="Offer Product", status=self.active_status)
        product.categories.add(self.category)
        variant = ProductVariants.objects.create(
            product=product,
            sku="SKU-OFFER-1",
            combination_key="1:1",
        )

        from domains.vendor.views.products import VendorProductVariantDetailView

        factory = APIRequestFactory()
        request = factory.patch(
            f"/vendor/variants/{variant.id}",
            {"price": "150.00", "discount_type": "percentage", "discount_value": "10.00"},
            format="json",
        )
        force_authenticate(request, user=self.vendor)

        response = VendorProductVariantDetailView.as_view()(request, variant_id=variant.id)

        self.assertEqual(response.status_code, 200)
        offer = BusinessOffer.objects.get(business=business, variant=variant)
        self.assertEqual(str(offer.price), "150.00")
        self.assertEqual(offer.discount_type, "percentage")
        self.assertEqual(str(offer.discount_value), "10.00")

    def test_find_similar_products_empty_name(self):
        Product.objects.create(name="Samsung Galaxy", status=self.active_status)
        results = VendorProductService.find_similar_products("")
        self.assertEqual(len(results), 0)

    def test_find_similar_products_limit(self):
        for i in range(15):
            Product.objects.create(
                name=f"Product {i} Samsung Galaxy", status=self.active_status
            )
        results = VendorProductService.find_similar_products(
            "Samsung Galaxy", limit=5
        )
        self.assertLessEqual(len(results), 5)

    # ─────────────────────── get_editable_annotation ───────────────────────

    def test_editable_annotation_wait_for_admin_confirmation(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        from django.db.models import Value
        qs = Product.objects.filter(pk=product.pk).annotate(
            editable=VendorProductService.get_editable_annotation(self.vendor)
        )
        self.assertTrue(qs.first().editable)

    def test_editable_annotation_admin_rejected(self):
        product = self._make_product(
            status=self.rejected_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        qs = Product.objects.filter(pk=product.pk).annotate(
            editable=VendorProductService.get_editable_annotation(self.vendor)
        )
        self.assertTrue(qs.first().editable)

    def test_editable_annotation_active_is_false(self):
        product = self._make_product(
            status=self.active_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        qs = Product.objects.filter(pk=product.pk).annotate(
            editable=VendorProductService.get_editable_annotation(self.vendor)
        )
        self.assertFalse(qs.first().editable)

    def test_editable_annotation_other_vendor_is_false(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.other_vendor, creator_model="vendor.vendor"
        )
        qs = Product.objects.filter(pk=product.pk).annotate(
            editable=VendorProductService.get_editable_annotation(self.vendor)
        )
        self.assertFalse(qs.first().editable)

    # ─────────────────────── get_created_by_me_annotation ───────────────────────

    def test_created_by_me_true(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        qs = Product.objects.filter(pk=product.pk).annotate(
            created_by_me=VendorProductService.get_created_by_me_annotation(self.vendor)
        )
        self.assertTrue(qs.first().created_by_me)

    def test_created_by_me_false_for_other_vendor(self):
        product = self._make_product(
            status=self.wait_status, vendor=self.other_vendor, creator_model="vendor.vendor"
        )
        qs = Product.objects.filter(pk=product.pk).annotate(
            created_by_me=VendorProductService.get_created_by_me_annotation(self.vendor)
        )
        self.assertFalse(qs.first().created_by_me)

    def test_created_by_me_false_for_admin_created(self):
        product = self._make_product(status=self.pending_status)
        qs = Product.objects.filter(pk=product.pk).annotate(
            created_by_me=VendorProductService.get_created_by_me_annotation(self.vendor)
        )
        self.assertFalse(qs.first().created_by_me)
