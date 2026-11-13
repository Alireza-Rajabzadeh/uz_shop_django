from django.test import TestCase

from core.management.seeders.developing.customers import CustomerSeeder, TEST_CUSTOMER_PASSWORD
from domains.customer.models import Customer, CustomerAddress, CustomerPreference
from domains.location.models import City, Country, State


class CustomerSeederTests(TestCase):
    def setUp(self):
        country = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        state = State.objects.create(country=country, name="Tehran")
        for index in range(1, 6):
            City.objects.create(state=state, name=f"Test City {index}")

    def test_customer_fixtures_are_complete_idempotent_and_isolated(self):
        seeder = CustomerSeeder()
        seeder.run()

        fixtures = Customer.objects.filter(email__endswith="@uzshop.local")
        self.assertEqual(fixtures.count(), 100)
        self.assertEqual(CustomerPreference.objects.filter(customer__in=fixtures).count(), 100)
        self.assertEqual(CustomerAddress.objects.filter(customer__in=fixtures).count(), 199)
        self.assertEqual(
            CustomerAddress.objects.filter(customer__in=fixtures, is_default=True).count(),
            100,
        )
        for status_id in range(1, 5):
            self.assertEqual(fixtures.filter(status_id=status_id).count(), 25)

        first = fixtures.get(phone="09990000001")
        self.assertTrue(first.check_password(TEST_CUSTOMER_PASSWORD))
        for address in CustomerAddress.objects.filter(customer__in=fixtures).select_related(
            "country", "state", "city"
        ):
            self.assertEqual(address.state.country_id, address.country_id)
            self.assertEqual(address.city.state_id, address.state_id)

        real_customer = Customer.objects.create_user(
            phone="09120000999",
            password="RealPassword123!",
            first_name="Real",
            last_name="Customer",
            email="real@example.com",
            customer_code="CUS-90000",
            status_id=1,
        )
        seeder.run()

        self.assertEqual(Customer.objects.filter(email__endswith="@uzshop.local").count(), 100)
        self.assertEqual(CustomerAddress.objects.filter(customer__in=fixtures).count(), 199)
        real_customer.refresh_from_db()
        self.assertEqual(real_customer.email, "real@example.com")
