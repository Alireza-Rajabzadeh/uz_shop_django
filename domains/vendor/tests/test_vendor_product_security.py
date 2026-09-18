from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.services.vendor_product_service import VendorProductService


class VendorProductSecurityTests(TestCase):
    def setUp(self):
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
        self.category_status, _ = CategoryStatus.objects.get_or_create(
            name="active", defaults={"name": "active"}
        )
        self.category, _ = Category.objects.get_or_create(
            name="Phones", defaults={"status": self.category_status}
        )
        self.wait_status, _ = ProductStatus.objects.get_or_create(
            name="wait_for_admin_confirmation"
        )
        self.active_status, _ = ProductStatus.objects.get_or_create(
            name="active"
        )
        self.rejected_status, _ = ProductStatus.objects.get_or_create(
            name="admin_rejected"
        )

    def _make_product(self, status=None, vendor=None, creator_model=""):
        if status is None:
            status = self.wait_status
        product = Product.objects.create(name="Test Product", status=status)
        product.categories.add(self.category)
        if vendor:
            product.created_by_vendor = vendor
            product.creator_model = creator_model
            product.save(update_fields=["created_by_vendor", "creator_model"])
        return product

    def test_update_rejects_different_vendor(self):
        product = self._make_product(vendor=self.other_vendor, creator_model="vendor.vendor")
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Hacked",
                category_ids=[self.category.id],
            )

    def test_update_rejects_active_status(self):
        product = self._make_product(status=self.active_status, vendor=self.vendor, creator_model="vendor.vendor")
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail",
                category_ids=[self.category.id],
            )

    def test_update_rejects_creator_model_not_vendor(self):
        product = self._make_product(vendor=self.vendor, creator_model="catalog.product")
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail",
                category_ids=[self.category.id],
            )

    def test_update_resets_status_to_wait_for_admin(self):
        product = self._make_product(vendor=self.vendor, creator_model="vendor.vendor")
        VendorProductService.update_vendor_product(
            product, self.vendor, name="Updated",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

    def test_update_from_rejected_resets_to_wait_for_admin(self):
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

    def test_update_preserves_created_by_vendor(self):
        product = self._make_product(vendor=self.vendor, creator_model="vendor.vendor")
        VendorProductService.update_vendor_product(
            product, self.vendor, name="Updated",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(product.creator_model, "vendor.vendor")

    def test_update_extra_kwargs_are_ignored(self):
        product = self._make_product(vendor=self.vendor, creator_model="vendor.vendor")
        with self.assertRaises(TypeError):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Updated",
                category_ids=[self.category.id],
                status=self.active_status.pk,
                created_by_vendor=self.other_vendor.pk,
                creator_model="catalog.product",
                slug="hacked-slug",
            )

    def test_create_vendor_product_sets_correct_status(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Product",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(product.creator_model, "vendor.vendor")

    def test_cannot_add_variant_while_pending(self):
        product = self._make_product(vendor=self.vendor, creator_model="vendor.vendor")
        self.assertFalse(VendorProductService.can_add_variant(product))

    def test_cannot_add_variant_while_rejected(self):
        product = self._make_product(
            status=self.rejected_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertFalse(VendorProductService.can_add_variant(product))

    def test_can_add_variant_when_active(self):
        product = self._make_product(
            status=self.active_status, vendor=self.vendor, creator_model="vendor.vendor"
        )
        self.assertTrue(VendorProductService.can_add_variant(product))
