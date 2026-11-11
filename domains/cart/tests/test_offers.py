from decimal import Decimal

from domains.business.models import BusinessProfile
from domains.cart.models import CartItem
from domains.inventory.models import Inventory, Warehouse
from domains.marketplace.models import BusinessOffer

from .base import CartBaseAPITestCase


class CartOffersAPITests(CartBaseAPITestCase):
    def test_cart_uses_the_cheapest_in_stock_offer(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, price="100.00", available=8, quantity=10)
        second_business = BusinessProfile.objects.create(
            vendor=None,
            business_name="Cart Second Business",
            display_name="Cart Second Business",
        )
        second_warehouse = Warehouse.objects.create(
            code="WH-CART-2",
            name="Second Cart Warehouse",
            business=second_business,
            city=self.city,
            address="Second test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        BusinessOffer.objects.create(
            business=second_business,
            variant=variant,
            price=Decimal("80.00"),
        )
        Inventory.objects.create(
            business=second_business,
            variant=variant,
            warehouse=second_warehouse,
            quantity=3,
            sellable=3,
            reserved=0,
            min_stock=0,
        )

        response = self.add_item(variant, quantity=1)

        self.assertEqual(response.status_code, 201, response.data)
        item = response.data["data"]["items"][0]
        self.assertEqual(item["unit_price"], "80.00")
        self.assertEqual(item["available"], 3)
        self.assertEqual(item["business"]["id"], second_business.id)
        self.assertEqual(item["business"]["name"], "Cart Second Business")
        self.assertTrue(item["valid"])

        response = self.add_item(variant, quantity=4)

        self.assertEqual(response.status_code, 201, response.data)
        item = response.data["data"]["items"][0]
        self.assertEqual(item["quantity"], 4)
        self.assertEqual(item["available"], 3)
        self.assertEqual(item["business"]["id"], second_business.id)
        self.assertEqual(item["business"]["name"], "Cart Second Business")
        self.assertFalse(item["valid"])

    def test_cart_can_pin_a_selected_seller_offer(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, price="100.00", available=8, quantity=10)
        primary_offer = BusinessOffer.objects.get(
            business=self.business, variant=variant
        )
        second_business = BusinessProfile.objects.create(
            vendor=None,
            business_name="Cart Pinned Business",
            display_name="Cart Pinned Business",
        )
        second_warehouse = Warehouse.objects.create(
            code="WH-CART-PIN",
            name="Pinned Cart Warehouse",
            business=second_business,
            city=self.city,
            address="Pinned test address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        second_offer = BusinessOffer.objects.create(
            business=second_business,
            variant=variant,
            price=Decimal("80.00"),
        )
        Inventory.objects.create(
            business=second_business,
            variant=variant,
            warehouse=second_warehouse,
            quantity=3,
            sellable=3,
            reserved=0,
            min_stock=0,
        )

        response = self.client.post(
            "/api/cart/items",
            {
                "variant_id": variant.id,
                "offer_id": primary_offer.id,
                "quantity": 4,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        item = response.data["data"]["items"][0]
        self.assertEqual(item["offer_id"], primary_offer.id)
        self.assertEqual(item["business"]["id"], self.business.id)
        self.assertEqual(item["business"]["name"], self.business.display_name)
        self.assertEqual(item["unit_price"], "100.00")
        self.assertEqual(item["available"], 8)
        self.assertTrue(item["valid"])
        self.assertEqual(
            CartItem.objects.get(cart__customer=self.customer).offer_id,
            primary_offer.id,
        )

        switched = self.client.post(
            "/api/cart/items",
            {
                "variant_id": variant.id,
                "offer_id": second_offer.id,
                "quantity": 1,
            },
            format="json",
        )
        self.assertEqual(switched.status_code, 201, switched.data)
        item = switched.data["data"]["items"][0]
        self.assertEqual(item["offer_id"], second_offer.id)
        self.assertEqual(item["business"]["id"], second_business.id)
        self.assertEqual(item["business"]["name"], "Cart Pinned Business")
        self.assertEqual(item["unit_price"], "80.00")

    def test_cart_rejects_an_offer_for_another_variant(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product)
        other_product = self.make_product(self.active_status)
        other_variant = self.make_variant(other_product)
        other_offer = BusinessOffer.objects.get(
            business=self.business, variant=other_variant
        )

        response = self.client.post(
            "/api/cart/items",
            {
                "variant_id": variant.id,
                "offer_id": other_offer.id,
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("offer_id", response.data["errors"])

    def test_guest_validate_can_pin_a_selected_seller_offer(self):
        product = self.make_product(self.active_status)
        variant = self.make_variant(product, price="100.00", available=8, quantity=10)
        primary_offer = BusinessOffer.objects.get(
            business=self.business, variant=variant
        )
        second_business = BusinessProfile.objects.create(
            vendor=None,
            business_name="Guest Pinned Business",
            display_name="Guest Pinned Business",
        )
        second_warehouse = Warehouse.objects.create(
            code="WH-CART-GUEST-PIN",
            name="Guest Pinned Warehouse",
            business=second_business,
            city=self.city,
            address="Guest pinned address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        BusinessOffer.objects.create(
            business=second_business,
            variant=variant,
            price=Decimal("70.00"),
        )
        Inventory.objects.create(
            business=second_business,
            variant=variant,
            warehouse=second_warehouse,
            quantity=2,
            sellable=2,
            reserved=0,
            min_stock=0,
        )

        response = self.client.post(
            "/api/cart/validate",
            {
                "variant_id": variant.id,
                "offer_id": primary_offer.id,
                "quantity": 4,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        item = response.data["data"]
        self.assertEqual(item["offer_id"], primary_offer.id)
        self.assertEqual(item["business"]["id"], self.business.id)
        self.assertEqual(item["business"]["name"], self.business.display_name)
        self.assertEqual(item["unit_price"], "100.00")
        self.assertEqual(item["available"], 8)
        self.assertTrue(item["valid"])
