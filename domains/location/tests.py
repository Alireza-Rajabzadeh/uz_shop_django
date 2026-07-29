from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.customer.models import Customer, CustomerStatus
from domains.location.models import City, Country, State


class AdminLocationOptionAPITests(APITestCase):
    def setUp(self):
        self.iran = Country.objects.create(name="Iran", code="IR", phone_code="+98")
        self.turkey = Country.objects.create(name="Turkey", code="TR", phone_code="+90")
        self.tehran = State.objects.create(country=self.iran, name="Tehran")
        self.istanbul = State.objects.create(country=self.turkey, name="Istanbul")
        self.tehran_city = City.objects.create(state=self.tehran, name="Tehran")
        City.objects.create(state=self.istanbul, name="Istanbul")
        self.admin = User.objects.create_user(
            username="location-admin", password="password", is_staff=True
        )

    def grant(self, *codenames):
        permissions = Permission.objects.filter(
            content_type__app_label="customer", codename__in=codenames
        )
        self.admin.user_permissions.add(*permissions)
        self.admin = User.objects.get(pk=self.admin.pk)
        self.client.force_authenticate(self.admin)

    def test_location_options_require_address_view_permission_and_filter_hierarchy(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/customer/location-options/countries").status_code, 403)

        self.grant("view_customeraddress")
        countries = self.client.get("/api/customer/location-options/countries")
        states = self.client.get(
            f"/api/customer/location-options/states?country_id={self.iran.id}"
        )
        cities = self.client.get(
            f"/api/customer/location-options/cities?state_id={self.tehran.id}"
        )
        self.assertEqual(countries.status_code, 200)
        self.assertEqual([item["id"] for item in states.data["data"]], [self.tehran.id])
        self.assertEqual([item["id"] for item in cities.data["data"]], [self.tehran_city.id])
        self.assertEqual(self.client.get("/api/customer/location-options/states").status_code, 400)

    def test_customer_principal_cannot_use_location_options(self):
        status = CustomerStatus.objects.create(name="location-active", title="Active")
        customer = Customer.objects.create_user(
            phone="09123333333", password="password", first_name="Location",
            last_name="Customer", customer_code="CUS-30001", status=status,
        )
        refresh = RefreshToken.for_user(customer)
        refresh["user_type"] = "customer"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = self.client.get("/api/customer/location-options/countries")
        self.assertEqual(response.status_code, 401)

    def test_warehouse_permission_can_use_location_owned_options(self):
        permission = Permission.objects.get(
            content_type__app_label="inventory", codename="add_warehouse"
        )
        self.admin.user_permissions.add(permission)
        self.client.force_authenticate(User.objects.get(pk=self.admin.pk))
        response = self.client.get("/api/location/options/countries")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 2)


class LocationRootURLTests(APITestCase):
    def test_location_crud_is_mounted(self):
        admin = User.objects.create_superuser("location-root", password="password")
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/location/countries").status_code, 200)


@override_settings(ROOT_URLCONF="domains.location.urls")
class LocationCRUDAPITests(APITestCase):
    def setUp(self):
        self.iran = Country.objects.create(
            name="Iran", fa_title="ایران", code="IR", phone_code="+98"
        )
        self.turkey = Country.objects.create(
            name="Turkey", fa_title="ترکیه", code="TR", phone_code="+90"
        )
        self.tehran = State.objects.create(country=self.iran, name="Tehran")
        self.tehran_city = City.objects.create(state=self.tehran, name="Tehran")
        self.admin = User.objects.create_user(
            username="location-crud-admin", password="password", is_staff=True
        )

    def authenticate(self, *codenames):
        permissions = Permission.objects.filter(
            content_type__app_label="location", codename__in=codenames
        )
        self.admin.user_permissions.add(*permissions)
        self.admin = User.objects.get(pk=self.admin.pk)
        self.client.force_authenticate(self.admin)

    def test_superuser_can_create_read_update_and_delete_country(self):
        superuser = User.objects.create_superuser("root", "root@example.com", "password")
        self.client.force_authenticate(superuser)
        created = self.client.post("/countries", {
            "name": "  New   Zealand ", "fa_title": " نیوزیلند ",
            "code": "nz", "phone_code": "64",
        })
        self.assertEqual(created.status_code, 201)
        country_id = created.data["data"]["id"]
        self.assertEqual(created.data["data"]["name"], "New Zealand")
        self.assertEqual(created.data["data"]["code"], "NZ")
        self.assertEqual(created.data["data"]["phone_code"], "+64")
        self.assertEqual(self.client.get(f"/countries/{country_id}").status_code, 200)
        updated = self.client.patch(f"/countries/{country_id}", {"fa_title": "  نو   زیلند "})
        self.assertEqual(updated.data["data"]["fa_title"], "نو زیلند")
        self.assertEqual(self.client.delete(f"/countries/{country_id}").status_code, 200)

    def test_superuser_can_crud_complete_hierarchy(self):
        superuser = User.objects.create_superuser("hierarchy-root", "hierarchy@example.com", "password")
        self.client.force_authenticate(superuser)
        country = self.client.post("/countries", {
            "name": "Kazakhstan", "code": "KZ", "phone_code": "+7",
        }).data["data"]
        state = self.client.post("/states", {
            "country": country["id"], "name": "Almaty Region",
        }).data["data"]
        city = self.client.post("/cities", {
            "state": state["id"], "name": "Almaty",
        }).data["data"]
        updated = self.client.patch(f"/cities/{city['id']}", {"fa_title": "آلماتی"})
        self.assertEqual(updated.data["data"]["fa_title"], "آلماتی")
        self.assertEqual(self.client.delete(f"/cities/{city['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/states/{state['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/countries/{country['id']}").status_code, 200)

    def test_native_model_permissions_apply_per_method(self):
        self.authenticate("view_country")
        self.assertEqual(self.client.get("/countries").status_code, 200)
        self.assertEqual(self.client.post("/countries", {
            "name": "Oman", "code": "OM", "phone_code": "+968"
        }).status_code, 403)
        self.assertEqual(self.client.get("/states").status_code, 403)

    def test_detail_urls_do_not_accept_create_requests(self):
        superuser = User.objects.create_superuser("detail-root", password="password")
        self.client.force_authenticate(superuser)
        self.assertEqual(self.client.post(f"/countries/{self.iran.id}", {}).status_code, 405)
        self.assertEqual(self.client.post(f"/states/{self.tehran.id}", {}).status_code, 405)
        self.assertEqual(self.client.post(f"/cities/{self.tehran_city.id}", {}).status_code, 405)

    def test_lists_filter_search_order_paginate_and_include_counts(self):
        Country.objects.bulk_create([
            Country(name=f"Page Country {index}", code=f"A{chr(65 + index)}", phone_code="+1")
            for index in range(21)
        ])
        self.authenticate("view_country", "view_state", "view_city")
        countries = self.client.get("/countries?search=ir&ordering=-name")
        self.assertEqual(countries.data["data"]["count"], 1)
        self.assertEqual(countries.data["data"]["results"][0]["state_count"], 1)
        self.assertFalse(countries.data["data"]["results"][0]["can_delete"])
        second_page = self.client.get("/countries?page=2&ordering=id")
        self.assertEqual(second_page.data["data"]["count"], 23)
        self.assertEqual(len(second_page.data["data"]["results"]), 3)
        states = self.client.get(f"/states?country_id={self.iran.id}")
        self.assertEqual([row["id"] for row in states.data["data"]["results"]], [self.tehran.id])
        cities = self.client.get(
            f"/cities?country_id={self.iran.id}&state_id={self.tehran.id}&ordering=name"
        )
        self.assertEqual(cities.data["data"]["results"][0]["country"], self.iran.id)

    def test_hierarchy_and_normalized_duplicates_are_rejected(self):
        self.authenticate("add_country", "add_state", "add_city")
        duplicate_country = self.client.post("/countries", {
            "name": " iran ", "code": "XY", "phone_code": "+1"
        })
        self.assertEqual(duplicate_country.status_code, 400)
        duplicate_state = self.client.post("/states", {
            "country": self.iran.id, "name": " tehran "
        })
        self.assertEqual(duplicate_state.status_code, 400)
        allowed_other_parent = self.client.post("/states", {
            "country": self.turkey.id, "name": "Tehran"
        })
        self.assertEqual(allowed_other_parent.status_code, 201)
        self.assertEqual(self.client.post("/cities", {
            "state": 999999, "name": "Missing Parent"
        }).status_code, 400)

    def test_database_constraints_cover_normalized_names(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Country.objects.create(name=" iran ", code="XX", phone_code="+1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            State.objects.create(country=self.iran, name=" tehran ")
        with self.assertRaises(IntegrityError), transaction.atomic():
            City.objects.create(state=self.tehran, name=" tehran ")

    def test_hierarchy_deletion_blockers_return_counts(self):
        self.authenticate("delete_country", "delete_state", "delete_city")
        country = self.client.delete(f"/countries/{self.iran.id}")
        self.assertEqual(country.status_code, 400)
        self.assertEqual(country.data["errors"]["blockers"]["states"], "1")
        state = self.client.delete(f"/states/{self.tehran.id}")
        self.assertEqual(state.status_code, 400)
        self.assertEqual(state.data["errors"]["blockers"]["cities"], "1")

    def test_city_address_and_warehouse_blockers_are_annotated_and_safe(self):
        from domains.customer.models import Customer, CustomerAddress, CustomerStatus
        from domains.inventory.models import Warehouse, WarehouseStatus

        customer_status = CustomerStatus.objects.create(name="loc-active", title="Active")
        customer = Customer.objects.create_user(
            phone="09120000123", password="password", first_name="A", last_name="B",
            customer_code="CUS-LOC-1", status=customer_status,
        )
        CustomerAddress.objects.create(
            customer=customer, title="Home", country=self.iran, state=self.tehran,
            city=self.tehran_city, postal_code="123", address_line1="Street",
        )
        warehouse_status = WarehouseStatus.objects.create(name="loc-active")
        Warehouse.objects.create(
            code="LOC-WH", name="Location WH", city=self.tehran_city, address="Street",
            lat=35, lng=51, status=warehouse_status,
        )
        self.authenticate("view_city", "delete_city")
        detail = self.client.get(f"/cities/{self.tehran_city.id}").data["data"]
        self.assertEqual(detail["address_count"], 1)
        self.assertEqual(detail["warehouse_count"], 1)
        self.assertFalse(detail["can_delete"])
        deleted = self.client.delete(f"/cities/{self.tehran_city.id}")
        self.assertEqual(deleted.status_code, 400)
        self.assertEqual(deleted.data["errors"]["blockers"], {
            "customer_addresses": "1", "warehouses": "1",
        })
