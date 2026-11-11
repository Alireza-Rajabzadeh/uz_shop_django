from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from domains.cart.models import Cart
from domains.customer.models import Customer, CustomerStatus


class CartAdminAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09120000201",
            password="password",
            first_name="Cart",
            last_name="Admin",
            customer_code="CUS-CART-101",
            status=self.active,
        )
        self.admin = User.objects.create_superuser("cart-admin", password="password")
        self.client.force_authenticate(self.admin)
        self.cart = Cart.objects.create(customer=self.customer)

    def test_admin_list_shows_cart_row(self):
        response = self.client.get("/api/cart/admin/carts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        row = response.data["data"]["results"][0]
        self.assertEqual(row["id"], self.cart.id)
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["items_count"], 0)
        self.assertFalse(row["has_address"])

    def test_admin_list_filters_by_search(self):
        response = self.client.get("/api/cart/admin/carts", {"search": "Admin"})
        self.assertEqual(response.data["data"]["count"], 1)
        response = self.client.get("/api/cart/admin/carts", {"search": "no-match"})
        self.assertEqual(response.data["data"]["count"], 0)

    def test_admin_detail(self):
        response = self.client.get(f"/api/cart/admin/carts/{self.cart.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], self.cart.id)
        self.assertEqual(response.data["data"]["customer"]["id"], self.customer.id)
        self.assertEqual(response.data["data"]["items"], [])

    def test_admin_detail_missing_is_404(self):
        response = self.client.get("/api/cart/admin/carts/999999")
        self.assertEqual(response.status_code, 404)

    def test_customer_principal_cannot_use_admin_endpoints(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/cart/admin/carts").status_code, 403)

    def test_staff_without_permission_is_rejected(self):
        staff = User.objects.create_user(
            username="cart-noperm", password="password", is_staff=True
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get("/api/cart/admin/carts").status_code, 403)
