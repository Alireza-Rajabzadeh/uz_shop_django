from domains.customer.models import CustomerAddress
from domains.location.models import City, Country, State

from .base import CartBaseAPITestCase


class CartAddressAPITests(CartBaseAPITestCase):
    def test_address_copied_from_saved_address(self):
        address = CustomerAddress.objects.create(
            customer=self.customer,
            title="Home",
            country=Country.objects.get(),
            state=State.objects.get(),
            city=self.city,
            postal_code="1234567890",
            address_line1="Main Street 1",
            is_default=True,
        )
        response = self.client.put(
            "/api/cart/address", {"saved_address_id": address.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        info = response.data["data"]
        self.assertEqual(info["country_name"], "Cart Country")
        self.assertEqual(info["address_line1"], "Main Street 1")
        self.assertEqual(info["receiver_name"], "Cart Owner")
        self.assertEqual(info["receiver_phone"], "09120000201")

    def test_address_saved_with_receiver_requires_both(self):
        product = self.make_product(self.preorder_status)
        variant = self.make_variant(product)
        item = self.add_item(variant)
        self.add_item(variant)
        item_id = item.data["data"]["items"][0]["id"]

        response = self.client.put(
            "/api/cart/address",
            {"saved_address_id": 12345, "receiver_name": "Only"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("receiver_name", response.data["errors"])

    def test_address_manual_requires_full_address(self):
        response = self.client.put(
            "/api/cart/address",
            {"address_line1": "Only a line"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("address", response.data["errors"])

    def test_address_manual_hierarchy_validated(self):
        country = Country.objects.get(code="CC")
        wrong_state = State.objects.create(name="Other State", country=country)
        wrong_city = City.objects.create(name="Wrong City", state=wrong_state)
        response = self.client.put(
            "/api/cart/address",
            {
                "country_id": country.id,
                "state_id": State.objects.get(country=country, name="Cart State").id,
                "city_id": wrong_city.id,
                "postal_code": "123",
                "address_line1": "Street 2",
                "receiver_name": "Receiver",
                "receiver_phone": "09120000202",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("city_id", response.data["errors"])
