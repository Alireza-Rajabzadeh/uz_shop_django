from domains.cart.models import CartItem

from .base import CartBaseAPITestCase


class CartSyncAndMergeAPITests(CartBaseAPITestCase):
    def test_sync_keeps_existing_variants(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 3}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["removed"], [])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertTrue(CartItem.objects.filter(cart__customer=self.customer).exists())

    def test_sync_merges_quantity(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.sync_items([{"variant_id": variant.id, "quantity": 2}])
        response = self.sync_items([{"variant_id": variant.id, "quantity": 5}])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_sync_reports_missing_variant(self):
        response = self.sync_items([{"variant_id": 999999, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["variant_id"], 999999)
        self.assertEqual(removed[0]["suggested_action"], "remove")
        self.assertIsNone(removed[0]["product_id"])
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_reports_preorder_product(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["product_id"], product.id)
        self.assertEqual(removed[0]["suggested_action"], "preorder")
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_reports_inactive_product(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        product.status = self.inactive_status
        product.save(update_fields=["status"])
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["product_id"], product.id)
        self.assertEqual(removed[0]["suggested_action"], "wishlist")
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_sync_keeps_out_of_stock_active_product(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, available=0, quantity=0)
        response = self.sync_items([{"variant_id": variant.id, "quantity": 1}])
        self.assertEqual(response.data["data"]["removed"], [])
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["status"], "out_of_stock")

    def test_sync_empty_items_returns_current_cart(self):
        response = self.sync_items([])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["removed"], [])
        self.assertEqual(response.data["data"]["cart"]["items"], [])

    def test_merge_adds_guest_items(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        response = self.client.post(
            "/api/cart/merge",
            {"items": [{"variant_id": variant.id, "quantity": 3}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        cart = response.data["data"]["cart"]
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertTrue(CartItem.objects.filter(cart__customer=self.customer).exists())

    def test_merge_reports_unavailable_guest_items(self):
        response = self.client.post(
            "/api/cart/merge",
            {"items": [{"variant_id": 999999, "quantity": 1}]},
            format="json",
        )
        removed = response.data["data"]["removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["variant_id"], 999999)
        self.assertEqual(removed[0]["suggested_action"], "remove")
