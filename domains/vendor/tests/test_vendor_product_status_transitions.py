from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.services.vendor_product_service import VendorProductService


class VendorProductStatusTransitionTests(TestCase):
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

    def test_vendor_creates_product_pending_confirmation(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(product.creator_model, "vendor.vendor")

    def test_admin_confirms_vendor_product_to_active(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.status = self.active_status
        product.save(update_fields=["status"])
        product.refresh_from_db()
        self.assertEqual(product.status.name, "active")

    def test_admin_rejects_vendor_product(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.status = self.rejected_status
        product.save(update_fields=["status"])
        product.refresh_from_db()
        self.assertEqual(product.status.name, "admin_rejected")

    def test_vendor_edits_rejected_product_resubmits(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.status = self.rejected_status
        product.save(update_fields=["status"])

        VendorProductService.update_vendor_product(
            product, self.vendor, name="Fixed Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.name, "Fixed Phone")

    def test_vendor_edits_pending_product_resubmits(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

        VendorProductService.update_vendor_product(
            product, self.vendor, name="Updated Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

    def test_full_lifecycle_create_confirm_edit_reject_resubmit(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")

        product.status = self.active_status
        product.save(update_fields=["status"])
        product.refresh_from_db()
        self.assertEqual(product.status.name, "active")

        product.status = self.rejected_status
        product.save(update_fields=["status"])
        product.refresh_from_db()
        self.assertEqual(product.status.name, "admin_rejected")

        VendorProductService.update_vendor_product(
            product, self.vendor, name="Updated Phone",
            category_ids=[self.category.id],
        )
        product.refresh_from_db()
        self.assertEqual(product.status.name, "wait_for_admin_confirmation")
        self.assertEqual(product.name, "Updated Phone")

    def test_vendor_cannot_edit_active_product(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )
        product.status = self.active_status
        product.save(update_fields=["status"])

        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_vendor_cannot_edit_admin_created_product(self):
        product = Product.objects.create(
            name="Admin Product", status=self.pending_status
        )
        product.categories.add(self.category)

        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            VendorProductService.update_vendor_product(
                product, self.vendor, name="Should Fail"
            )

    def test_admin_can_change_status_via_patch(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor,
            name="New Phone",
            category_ids=[self.category.id],
        )

        admin = User.objects.create_superuser(
            username="admin", password="password"
        )
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
        admin = User.objects.create_superuser(
            username="admin", password="password"
        )
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

    def test_cannot_delete_wait_for_admin_confirmation_status(self):
        product = VendorProductService.create_vendor_product(
            vendor=self.vendor, name="T", category_ids=[self.category.id],
        )
        status = ProductStatus.objects.get(name="wait_for_admin_confirmation")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            status.delete()

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
