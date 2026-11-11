from rest_framework.test import APIClient

from domains.cart.models import Cart

from .base import CartBaseAPITestCase


class CartGuestValidationAPITests(CartBaseAPITestCase):
    def test_guest_validate_single_item(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertTrue(data["valid"])
        self.assertEqual(data["variant_id"], variant.id)
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["effective_price"], "100.00")
        self.assertFalse(data["quantity_capped"])

    def test_guest_validate_caps_quantity_to_inventory(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, available=3)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 5},
            format="json",
        )
        data = response.data["data"]
        self.assertTrue(data["valid"])
        self.assertEqual(data["quantity"], 3)
        self.assertEqual(data["requested_quantity"], 5)
        self.assertTrue(data["quantity_capped"])

    def test_guest_validate_missing_variant_is_invalid(self):
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate",
            {"variant_id": 999999, "quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertFalse(data["valid"])
        self.assertEqual(data["status"], "variant_unavailable")
        self.assertEqual(data["suggested_action"], "remove")

    def test_guest_validate_does_not_persist_cart(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        anon.post(
            "/api/cart/validate",
            {"variant_id": variant.id, "quantity": 1},
            format="json",
        )
        self.assertEqual(Cart.objects.count(), 0)

    def test_guest_bulk_validate_items(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        anon = APIClient()
        response = anon.post(
            "/api/cart/validate-items",
            {
                "items": [
                    {"variant_id": variant.id, "quantity": 1},
                    {"variant_id": 999999, "quantity": 2},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        items = response.data["data"]["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["valid"])
        self.assertFalse(items[1]["valid"])
        self.assertEqual(Cart.objects.count(), 0)

    def test_anonymous_get_validate_rejected(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/cart/validate").status_code, 401)
