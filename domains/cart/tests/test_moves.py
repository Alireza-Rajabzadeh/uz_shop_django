from domains.cart.models import CartItem
from domains.preorder.models import PreOrder
from domains.wishlist.models import Wishlist

from .base import CartBaseAPITestCase


class CartMovesAPITests(CartBaseAPITestCase):
    def test_moves_item_to_wishlist(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-wishlist")
        self.assertEqual(move.status_code, 200)
        self.assertTrue(Wishlist.objects.filter(customer=self.customer, product=product).exists())
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_move_to_wishlist_when_already_saved_still_removes(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        Wishlist.objects.create(customer=self.customer, product=product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-wishlist")
        self.assertEqual(move.status_code, 200)
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_moves_item_to_preorder_when_allowed(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-preorder")
        self.assertEqual(move.status_code, 200)
        self.assertTrue(PreOrder.objects.filter(customer=self.customer, product=product).exists())
        self.assertFalse(CartItem.objects.filter(id=item_id).exists())

    def test_move_to_preorder_rejected_when_not_allowed(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        move = self.client.post(f"/api/cart/items/{item_id}/move-to-preorder")
        self.assertEqual(move.status_code, 400)
        self.assertIn("product", move.data["errors"])
        self.assertTrue(CartItem.objects.filter(id=item_id).exists())
