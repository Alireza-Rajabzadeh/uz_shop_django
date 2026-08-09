from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.customer.models import Customer, CustomerStatus
from domains.preorder.models import PreOrder
from rest_framework.test import APITestCase


class PreOrderAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000101",
            password="password",
            first_name="PreOrder",
            last_name="Owner",
            customer_code="CUS-PRE-001",
            status=self.active,
        )
        self.client.force_authenticate(self.customer)
        category_status = CategoryStatus.objects.create(name="preorder-active")
        self.category = Category.objects.create(
            name="PreOrder Category", status=category_status
        )
        self.preorder_status = ProductStatus.objects.create(name="preorder")
        self.active_status = ProductStatus.objects.create(name="active")
        self.preorderable = Product.objects.create(
            name="PreOrder Product", status=self.preorder_status
        )
        self.active_product = Product.objects.create(
            name="Active Product", status=self.active_status
        )

    def test_non_preorderable_product_is_rejected(self):
        response = self.client.post(
            "/api/preorder/", {"product_id": self.active_product.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("product_id", response.data["errors"])
        self.assertFalse(PreOrder.objects.filter(customer=self.customer).exists())

    def test_add_list_exists_and_remove(self):
        add = self.client.post(
            "/api/preorder/", {"product_id": self.preorderable.id}, format="json"
        )
        self.assertEqual(add.status_code, 201)

        detail = self.client.get("/api/preorder/")
        self.assertEqual(detail.data["data"]["count"], 1)
        self.assertEqual(
            detail.data["data"]["results"][0]["product"]["id"], self.preorderable.id
        )

        exists = self.client.get(
            f"/api/preorder/exists?product_id={self.preorderable.id}"
        )
        self.assertTrue(exists.data["data"]["in_preorder"])

        remove = self.client.delete(f"/api/preorder/products/{self.preorderable.id}")
        self.assertEqual(remove.status_code, 200)
        self.assertFalse(
            PreOrder.objects.filter(
                customer=self.customer, product=self.preorderable
            ).exists()
        )

    def test_duplicate_product_is_rejected(self):
        self.client.post(
            "/api/preorder/", {"product_id": self.preorderable.id}, format="json"
        )
        duplicate = self.client.post(
            "/api/preorder/", {"product_id": self.preorderable.id}, format="json"
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(
            PreOrder.objects.filter(customer=self.customer).count(), 1
        )

    def test_entry_survives_later_status_change(self):
        self.client.post(
            "/api/preorder/", {"product_id": self.preorderable.id}, format="json"
        )
        self.preorderable.status = self.active_status
        self.preorderable.save(update_fields=["status"])

        exists = self.client.get(
            f"/api/preorder/exists?product_id={self.preorderable.id}"
        )
        self.assertTrue(exists.data["data"]["in_preorder"])
        self.assertEqual(
            PreOrder.objects.filter(
                customer=self.customer, product=self.preorderable
            ).count(),
            1,
        )

    def test_missing_product_is_rejected(self):
        response = self.client.post(
            "/api/preorder/", {"product_id": 999999}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_remove_missing_item_is_404(self):
        response = self.client.delete("/api/preorder/products/999999")
        self.assertEqual(response.status_code, 404)

    def test_requires_authenticated_customer(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/preorder/")
        self.assertIn(response.status_code, (401, 403))