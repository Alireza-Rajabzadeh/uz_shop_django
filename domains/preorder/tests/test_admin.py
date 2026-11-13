from django.contrib.auth.models import User
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.customer.models import Customer, CustomerStatus
from domains.preorder.models import PreOrder
from rest_framework.test import APITestCase


class PreOrderAdminAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000101",
            password="password",
            first_name="PreOrder",
            last_name="Admin",
            customer_code="CUS-PRE-101",
            status=self.active,
        )
        self.admin = User.objects.create_superuser("preorder-admin", password="password")
        self.client.force_authenticate(self.admin)
        category_status = CategoryStatus.objects.create(name="preorder-admin-active")
        self.category = Category.objects.create(
            name="Admin PreOrder Category", status=category_status
        )
        self.preorder_status = ProductStatus.objects.create(name="preorder")
        self.product = Product.objects.create(
            name="Admin PreOrder Product", status=self.preorder_status
        )
        self.product.categories.add(self.category)
        self.item = PreOrder.objects.create(
            customer=self.customer, product=self.product
        )

    def test_admin_list_is_paginated_and_shows_customer_and_product(self):
        response = self.client.get("/api/preorder/admin/preorders")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["id"], self.item.id)
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["product"]["id"], self.product.id)

    def test_admin_list_filters_by_search(self):
        response = self.client.get(
            "/api/preorder/admin/preorders", {"search": "Admin PreOrder Product"}
        )
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.get("/api/preorder/admin/preorders", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_detail(self):
        response = self.client.get(f"/api/preorder/admin/preorders/{self.item.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["customer"]["id"], self.customer.id)

    def test_admin_detail_missing_is_404(self):
        response = self.client.get("/api/preorder/admin/preorders/999999")
        self.assertEqual(response.status_code, 404)

    def test_customer_principal_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.get("/api/preorder/admin/preorders").status_code, 403
        )

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="preorder-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get("/api/preorder/admin/preorders").status_code, 403
        )
