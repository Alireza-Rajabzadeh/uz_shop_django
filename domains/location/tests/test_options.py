from django.contrib.auth.models import Permission, User
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
        # The permissioned namespace is /api/location/options/. These routes
        # started out on /api/customer/location-options/ and were repointed to a
        # public customer view by 34fa79f, which is why the assertions below
        # moved; that public contract is pinned by its own test underneath.
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/location/options/countries").status_code, 403)

        self.grant("view_customeraddress")
        countries = self.client.get("/api/location/options/countries")
        states = self.client.get(
            f"/api/location/options/states?country_id={self.iran.id}"
        )
        cities = self.client.get(
            f"/api/location/options/cities?state_id={self.tehran.id}"
        )
        self.assertEqual(countries.status_code, 200)
        self.assertEqual([item["id"] for item in states.data["data"]], [self.tehran.id])
        self.assertEqual([item["id"] for item in cities.data["data"]], [self.tehran_city.id])
        self.assertEqual(self.client.get("/api/location/options/states").status_code, 400)

    def test_customer_principal_cannot_use_location_options(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._customer_access_token()}")
        response = self.client.get("/api/location/options/countries")
        self.assertEqual(response.status_code, 401)

    def test_customer_location_options_are_public_reference_data(self):
        # An address form has to list countries before anyone has signed in,
        # and a customer holds no model permission to grant, so this namespace
        # is deliberately AllowAny. Pin it so the permission gate above does
        # not quietly get pushed back onto it.
        self.client.credentials()
        self.assertEqual(
            self.client.get("/api/customer/location-options/countries").status_code, 200
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._customer_access_token()}")
        self.assertEqual(
            self.client.get("/api/customer/location-options/countries").status_code, 200
        )

    def _customer_access_token(self):
        status = CustomerStatus.objects.create(name="location-active", title="Active")
        customer = Customer.objects.create_user(
            phone="09123333333", password="password", first_name="Location",
            last_name="Customer", customer_code="CUS-30001", status=status,
        )
        refresh = RefreshToken.for_user(customer)
        refresh["user_type"] = "customer"
        return str(refresh.access_token)

    def test_warehouse_permission_can_use_location_owned_options(self):
        permission = Permission.objects.get(
            content_type__app_label="inventory", codename="add_warehouse"
        )
        self.admin.user_permissions.add(permission)
        self.client.force_authenticate(User.objects.get(pk=self.admin.pk))
        response = self.client.get("/api/location/options/countries")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 2)
