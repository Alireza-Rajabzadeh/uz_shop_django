from datetime import date, datetime

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.customers import CustomerSeeder, TEST_CUSTOMER_PASSWORD
from domains.customer.models import (
    Customer,
    CustomerAddress,
    CustomerPreference,
    CustomerStatus,
)
from domains.location.models import City, Country, State


class AdminCustomerAPITests(APITestCase):
    def setUp(self):
        self.active = CustomerStatus.objects.create(name="active", title="Active")
        self.inactive = CustomerStatus.objects.create(name="inactive", title="Inactive")
        self.customer = Customer.objects.create_user(
            phone="09120000001", password="password", first_name="Ali",
            last_name="Ahmadi", customer_code="CUS-10001", status=self.active,
            email="ali@example.com", gender="male",
        )
        self.other_customer = Customer.objects.create_user(
            phone="09120000002", password="password", first_name="Sara",
            last_name="Karimi", customer_code="CUS-10002", status=self.inactive,
        )
        self.admin = User.objects.create_user(
            username="customer-admin", password="password", is_staff=True
        )

    def grant(self, *codenames):
        permissions = Permission.objects.filter(
            content_type__app_label="customer", codename__in=codenames
        )
        self.admin.user_permissions.add(*permissions)
        self.admin = User.objects.get(pk=self.admin.pk)
        self.client.force_authenticate(self.admin)

    def list_ids(self, **params):
        response = self.client.get("/api/customer/customers", params)
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.data["data"]["results"]]

    def test_customer_list_requires_model_permission(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 403)

        self.grant("view_customer")
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 2)

    def test_customer_token_is_rejected_from_admin_api(self):
        refresh = RefreshToken.for_user(self.customer)
        refresh["user_type"] = "customer"
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = self.client.get("/api/customer/customers")
        self.assertEqual(response.status_code, 401)

    def test_customer_filters_ordering_and_update_keep_code_immutable(self):
        self.grant("view_customer", "change_customer")
        response = self.client.get(
            f"/api/customer/customers?search=ali&status_id={self.active.id}&ordering=-phone"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["id"], self.customer.id)

        response = self.client.patch(
            f"/api/customer/customers/{self.customer.id}",
            {"first_name": "Alireza", "status_id": self.inactive.id, "customer_code": "CHANGED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Alireza")
        self.assertEqual(self.customer.status, self.inactive)
        self.assertEqual(self.customer.customer_code, "CUS-10001")

    def test_exact_id_and_existing_field_filters_are_anded(self):
        self.grant("view_customer")

        self.assertEqual(
            self.list_ids(
                id=self.customer.id,
                customer_code="1000",
                first_name="AL",
                last_name="mad",
                email="EXAMPLE",
                phone="000001",
                status_id=self.active.id,
                gender="male",
            ),
            [self.customer.id],
        )
        self.assertEqual(
            self.list_ids(id=self.customer.id, first_name="Sara"),
            [],
        )

        self.assertEqual(
            self.list_ids(ordering="gender"),
            [self.customer.id, self.other_customer.id],
        )

    def test_global_search_is_or_across_text_and_anded_with_filters(self):
        self.grant("view_customer")

        self.assertEqual(
            self.list_ids(search="CUS-10002", status_id=self.inactive.id),
            [self.other_customer.id],
        )
        self.assertEqual(
            self.list_ids(search="CUS-10002", status_id=self.active.id),
            [],
        )

    def test_date_of_birth_range_is_inclusive(self):
        self.grant("view_customer")
        self.customer.date_of_birth = date(1990, 5, 10)
        self.customer.save(update_fields=["date_of_birth"])
        self.other_customer.date_of_birth = date(1990, 5, 11)
        self.other_customer.save(update_fields=["date_of_birth"])

        self.assertEqual(
            self.list_ids(date_of_birth_from="1990-05-10", date_of_birth_to="1990-05-10"),
            [self.customer.id],
        )

    def test_verification_filters_are_tri_state_and_include_nulls_for_false(self):
        self.grant("view_customer")
        verified_at = timezone.make_aware(datetime(2026, 7, 20, 12, 0))
        Customer.objects.filter(pk=self.customer.pk).update(
            email_verified_at=verified_at,
            phone_verified_at=None,
        )
        Customer.objects.filter(pk=self.other_customer.pk).update(
            email_verified_at=None,
            phone_verified_at=verified_at,
        )

        self.assertEqual(set(self.list_ids()), {self.customer.id, self.other_customer.id})
        self.assertEqual(self.list_ids(email_verified="true"), [self.customer.id])
        self.assertEqual(self.list_ids(email_verified="false"), [self.other_customer.id])
        self.assertEqual(self.list_ids(phone_verified="true"), [self.other_customer.id])
        self.assertEqual(self.list_ids(phone_verified="false"), [self.customer.id])

    def test_login_presence_and_calendar_date_range_are_inclusive(self):
        self.grant("view_customer")
        Customer.objects.filter(pk=self.customer.pk).update(
            last_login=timezone.make_aware(datetime(2026, 7, 20, 23, 59, 59))
        )

        self.assertEqual(self.list_ids(has_logged_in="true"), [self.customer.id])
        self.assertEqual(self.list_ids(has_logged_in="false"), [self.other_customer.id])
        self.assertEqual(
            self.list_ids(last_login_from="2026-07-20", last_login_to="2026-07-20"),
            [self.customer.id],
        )

    def test_created_and_updated_calendar_date_ranges_are_inclusive_and_combine(self):
        self.grant("view_customer")
        boundary = timezone.make_aware(datetime(2026, 7, 15, 23, 59, 59))
        outside = timezone.make_aware(datetime(2026, 7, 16, 0, 0))
        Customer.objects.filter(pk=self.customer.pk).update(
            created_at=boundary,
            updated_at=boundary,
        )
        Customer.objects.filter(pk=self.other_customer.pk).update(
            created_at=outside,
            updated_at=outside,
        )

        self.assertEqual(
            self.list_ids(
                created_at_from="2026-07-15",
                created_at_to="2026-07-15",
                updated_at_from="2026-07-15",
                updated_at_to="2026-07-15",
                email_verified="false",
            ),
            [self.customer.id],
        )

    def test_invalid_date_ranges_return_field_errors(self):
        self.grant("view_customer")

        for prefix in ("date_of_birth", "last_login", "created_at", "updated_at"):
            with self.subTest(prefix=prefix):
                response = self.client.get(
                    "/api/customer/customers",
                    {f"{prefix}_from": "2026-07-21", f"{prefix}_to": "2026-07-20"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(f"{prefix}_to", response.data["errors"])


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


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
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
