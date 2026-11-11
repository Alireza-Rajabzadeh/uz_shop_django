from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from domains.customer.models import Customer, CustomerAddress, CustomerStatus
from domains.location.models import City, Country, State


class CustomerAddressAPITests(APITestCase):
    def setUp(self):
        status = CustomerStatus.objects.create(name="address-active", title="Active")
        self.customer = Customer.objects.create_user(
            phone="09121111111", password="password", first_name="One",
            last_name="Customer", customer_code="CUS-20001", status=status,
        )
        self.other_customer = Customer.objects.create_user(
            phone="09122222222", password="password", first_name="Other",
            last_name="Customer", customer_code="CUS-20002", status=status,
        )
        self.country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        self.other_country = Country.objects.create(name="Turkey", code="TR", phone_code="+90")
        self.state = State.objects.create(country=self.country, name="Tehran")
        self.other_state = State.objects.create(country=self.other_country, name="Istanbul")
        self.city = City.objects.create(state=self.state, name="Tehran")
        self.other_city = City.objects.create(state=self.other_state, name="Istanbul")
        self.address = self.make_address(self.customer, "Home")
        self.other_address = self.make_address(self.other_customer, "Other home")
        self.admin = User.objects.create_user(
            username="address-admin", password="password", is_staff=True
        )
        permissions = Permission.objects.filter(
            content_type__app_label="customer",
            codename__in=[
                "view_customeraddress", "add_customeraddress",
                "change_customeraddress", "delete_customeraddress",
            ],
        )
        self.admin.user_permissions.add(*permissions)
        self.client.force_authenticate(self.admin)

    def make_address(self, customer, title, is_default=False):
        return CustomerAddress.objects.create(
            customer=customer, title=title, country=self.country, state=self.state,
            city=self.city, postal_code="1234567890", address_line1="Street 1",
            is_default=is_default,
        )

    def payload(self, **overrides):
        data = {
            "title": "Office", "country": self.country.id, "state": self.state.id,
            "city": self.city.id, "postal_code": "9876543210",
            "address_line1": "Street 2", "is_default": False,
        }
        data.update(overrides)
        return data

    def test_nested_address_cannot_cross_customer_boundary(self):
        url = f"/api/customer/customers/{self.customer.id}/addresses/{self.other_address.id}"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"title": "Stolen"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.other_address.refresh_from_db()
        self.assertEqual(self.other_address.title, "Other home")

    def test_address_create_update_delete_and_hierarchy_validation(self):
        list_url = f"/api/customer/customers/{self.customer.id}/addresses"
        response = self.client.post(list_url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        address_id = response.data["data"]["id"]

        detail_url = f"{list_url}/{address_id}"
        response = self.client.patch(detail_url, {"title": "Work"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "Work")

        response = self.client.post(
            list_url, self.payload(state=self.other_state.id), format="json"
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(detail_url, {"city": self.other_city.id}, format="json")
        self.assertEqual(response.status_code, 400)

        self.assertEqual(self.client.delete(detail_url).status_code, 200)
        self.assertFalse(CustomerAddress.objects.filter(pk=address_id).exists())

    def test_setting_default_reassigns_and_database_rejects_duplicates(self):
        self.address.is_default = True
        self.address.save()
        list_url = f"/api/customer/customers/{self.customer.id}/addresses"
        response = self.client.post(
            list_url, self.payload(title="New default", is_default=True), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.address.refresh_from_db()
        self.assertFalse(self.address.is_default)
        self.assertEqual(
            CustomerAddress.objects.filter(customer=self.customer, is_default=True).count(), 1
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_address(self.customer, "Conflicting default", is_default=True)
