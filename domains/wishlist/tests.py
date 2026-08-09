from django.contrib.auth.models import User
from domains.catalog.models import Category, CategoryStatus, Product, ProductStatus
from domains.customer.models import Customer, CustomerStatus
from domains.wishlist.models import Wishlist
from rest_framework.test import APITestCase


class WishlistAdminAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000101",
            password="password",
            first_name="Wishlist",
            last_name="Admin",
            customer_code="CUS-WISH-101",
            status=self.active,
        )
        self.admin = User.objects.create_superuser("wishlist-admin", password="password")
        self.client.force_authenticate(self.admin)
        category_status = CategoryStatus.objects.create(name="wishlist-admin-active")
        product_status = ProductStatus.objects.create(name="wishlist-admin-status")
        self.category = Category.objects.create(
            name="Admin Category", status=category_status
        )
        self.product = Product.objects.create(
            name="Admin Product", status=product_status
        )
        self.product.categories.add(self.category)
        self.item = Wishlist.objects.create(
            customer=self.customer, product=self.product
        )

    def test_admin_list_is_paginated_and_shows_customer_and_product(self):
        response = self.client.get("/api/wishlist/admin/wishlists")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["id"], self.item.id)
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["customer"]["phone"], self.customer.phone)
        self.assertEqual(row["product"]["id"], self.product.id)

    def test_admin_list_filters_by_search(self):
        response = self.client.get("/api/wishlist/admin/wishlists", {"search": "Admin Product"})
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.get("/api/wishlist/admin/wishlists", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_detail(self):
        response = self.client.get(f"/api/wishlist/admin/wishlists/{self.item.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["customer"]["id"], self.customer.id)

    def test_admin_detail_missing_is_404(self):
        response = self.client.get("/api/wishlist/admin/wishlists/999999")
        self.assertEqual(response.status_code, 404)

    def test_customer_principal_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(
            self.client.get("/api/wishlist/admin/wishlists").status_code, 403
        )

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="wishlist-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get("/api/wishlist/admin/wishlists").status_code, 403
        )


class WishlistAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000001",
            password="password",
            first_name="Wishlist",
            last_name="Owner",
            customer_code="CUS-WISH-001",
            status=self.active,
        )
        self.client.force_authenticate(self.customer)
        self.category_status = CategoryStatus.objects.create(name="wishlist-active")
        self.product_status = ProductStatus.objects.create(name="wishlist-unknown")
        self.category = Category.objects.create(
            name="Wishlist Category", status=self.category_status
        )
        self.product = Product.objects.create(
            name="Wishlist Product", status=self.product_status
        )
        self.product.categories.add(self.category)

    @staticmethod
    def create_product(name, status_name):
        status = ProductStatus.objects.create(name=f"wishlist-{status_name}")
        product = Product.objects.create(name=name, status=status)
        product.categories.add(WishlistAPITests.category_for_tests())
        return product

    @staticmethod
    def category_for_tests():
        category_status = CategoryStatus.objects.create(name="wishlist-cat-active")
        return Category.objects.create(name="Wishlist Cat", status=category_status)

    def test_add_list_exists_and_remove(self):
        add = self.client.post(
            "/api/wishlist/", {"product_id": self.product.id}, format="json"
        )
        self.assertEqual(add.status_code, 201)
        self.assertEqual(add.data["data"]["product_id"], self.product.id)
        self.assertIsNone(add.data["errors"])

        detail = self.client.get("/api/wishlist/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["count"], 1)
        self.assertEqual(
            detail.data["data"]["results"][0]["product"]["id"], self.product.id
        )
        self.assertEqual(
            detail.data["data"]["results"][0]["product"]["category"]["id"],
            self.category.id,
        )

        exists = self.client.get(
            f"/api/wishlist/exists?product_id={self.product.id}"
        )
        self.assertEqual(exists.status_code, 200)
        self.assertTrue(exists.data["data"]["in_wishlist"])

        missing = self.client.get(
            "/api/wishlist/exists?product_id=99999"
        )
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.data["data"]["in_wishlist"])

        remove = self.client.delete(f"/api/wishlist/products/{self.product.id}")
        self.assertEqual(remove.status_code, 200)
        self.assertFalse(
            Wishlist.objects.filter(
                customer=self.customer, product=self.product
            ).exists()
        )

    def test_duplicate_product_is_rejected(self):
        self.client.post(
            "/api/wishlist/", {"product_id": self.product.id}, format="json"
        )
        duplicate = self.client.post(
            "/api/wishlist/", {"product_id": self.product.id}, format="json"
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertFalse(duplicate.data["success"])
        self.assertEqual(Wishlist.objects.filter(customer=self.customer).count(), 1)

    def test_missing_product_is_rejected(self):
        response = self.client.post(
            "/api/wishlist/", {"product_id": 999999}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("product_id", response.data["errors"])

    def test_unavailable_product_can_still_be_saved(self):
        unavailable = self.create_product("Out of stock", "inactive")
        response = self.client.post(
            "/api/wishlist/", {"product_id": unavailable.id}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Wishlist.objects.filter(customer=self.customer, product=unavailable).exists()
        )

    def test_remove_missing_item_is_404(self):
        response = self.client.delete("/api/wishlist/products/999999")
        self.assertEqual(response.status_code, 404)

    def test_requires_authenticated_customer(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/wishlist/")
        self.assertIn(response.status_code, (401, 403))

    def test_wishlist_is_per_customer(self):
        other = Customer.objects.create_user(
            phone="09120000002",
            password="password",
            first_name="Second",
            last_name="Owner",
            customer_code="CUS-WISH-002",
            status=self.active,
        )
        Wishlist.objects.create(customer=self.customer, product=self.product)
        self.assertEqual(
            Wishlist.objects.filter(customer=self.customer).count(), 1
        )
        self.assertEqual(Wishlist.objects.filter(customer=other).count(), 0)