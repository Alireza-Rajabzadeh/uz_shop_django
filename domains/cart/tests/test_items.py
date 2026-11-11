from domains.cart.models import Cart, CartItem

from .base import CartBaseAPITestCase


class CartItemsAPITests(CartBaseAPITestCase):
    def test_get_cart_creates_single_cart(self):
        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Cart.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(response.data["data"]["items"], [])

    def test_add_updates_existing_row_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        first = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(CartItem.objects.count(), 1)

        second = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 5},
            format="json",
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["data"]["items"][0]["quantity"], 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_add_requires_positive_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_add_missing_variant_rejected(self):
        response = self.client.post(
            "/api/cart/items", {"variant_id": 999999, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("variant_id", response.data["errors"])

    def test_update_and_remove_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        added = self.add_item(variant, quantity=3)
        item_id = added.data["data"]["items"][0]["id"]

        patch = self.client.patch(
            f"/api/cart/items/{item_id}", {"quantity": 7}, format="json"
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.data["data"]["items"][0]["quantity"], 7)

        zero = self.client.patch(
            f"/api/cart/items/{item_id}", {"quantity": 0}, format="json"
        )
        self.assertEqual(zero.status_code, 400)

        delete = self.client.delete(f"/api/cart/items/{item_id}")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.data["data"]["items"], [])
        self.assertEqual(CartItem.objects.filter(cart__customer=self.customer).count(), 0)

    def test_remove_missing_item_is_404(self):
        response = self.client.delete("/api/cart/items/999999")
        self.assertEqual(response.status_code, 404)

    def test_add_returns_full_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/items",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["variant_id"], variant.id)
        self.assertEqual(data["items"][0]["quantity"], 2)

    def test_clear_returns_empty_full_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant, quantity=2)

        response = self.client.post("/api/cart/clear")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["totals"]["total_amount"], "0.00")
        self.assertFalse(CartItem.objects.filter(cart__customer=self.customer).exists())
