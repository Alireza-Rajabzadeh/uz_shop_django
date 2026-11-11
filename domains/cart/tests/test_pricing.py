from decimal import Decimal

from domains.inventory.models import Inventory
from domains.marketplace.models import BusinessOffer

from .base import CartBaseAPITestCase


class CartPricingAndInventoryAPITests(CartBaseAPITestCase):
    def test_cart_shows_live_prices_and_discounts(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        offer = BusinessOffer.objects.get(business=self.business, variant=variant)
        offer.discount_type = "percentage"
        offer.discount_value = Decimal("10")
        offer.save(update_fields=["discount_type", "discount_value"])

        self.add_item(variant, quantity=2)
        data = self.client.get("/api/cart/?shipping=1").data["data"]
        item = data["items"][0]
        self.assertEqual(item["unit_price"], "100.00")
        self.assertEqual(item["effective_price"], "90.00")
        self.assertEqual(item["line_total"], "180.00")
        self.assertEqual(
            data["totals"]["shipment"],
            {"original_price": "200000.00", "final_price": "0.00"},
        )
        self.assertEqual(data["totals"]["shipping_amount"], "0.00")
        self.assertEqual(data["totals"]["total_amount"], "180.00")
        self.assertIn("combination_key", item)

    def test_unavailable_product_is_flagged(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant)
        product.status = self.inactive_status
        product.save(update_fields=["status"])

        data = self.client.get("/api/cart/").data["data"]
        item = data["items"][0]
        self.assertFalse(item["valid"])
        self.assertEqual(item["status"], "variant_unavailable")
        self.assertEqual(item["suggested_action"], "remove")
        self.assertFalse(data["cart_valid"])

    def test_insufficient_inventory_is_flagged(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant, quantity=5)
        stock = Inventory.objects.get(variant=variant)
        stock.sellable = 1
        stock.save(update_fields=["sellable"])

        data = self.client.get("/api/cart/").data["data"]
        item = data["items"][0]
        self.assertFalse(item["valid"])
        self.assertEqual(item["status"], "out_of_stock")
        self.assertFalse(data["cart_valid"])

    def test_validate_endpoint(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        self.add_item(variant)
        response = self.client.get("/api/cart/validate")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["valid"])
        self.assertEqual(response.data["data"]["items"][0]["status"], "available")

    def test_empty_cart_is_invalid_for_checkout(self):
        data = self.client.get("/api/cart/validate").data["data"]
        self.assertFalse(data["valid"])
