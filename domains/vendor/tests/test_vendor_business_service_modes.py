from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.business_service_modes import (
    BusinessServiceModeSeeder,
)
from domains.business.models import (
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessServiceMode,
)
from domains.vendor.models import Vendor, VendorStatus


class VendorBusinessServiceModeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        BusinessServiceModeSeeder().run()
        cls.online = BusinessServiceMode.objects.get(code="online")
        cls.in_person = BusinessServiceMode.objects.get(code="in_person")

        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        cls.vendor = Vendor.objects.create(
            phone="+989120000301",
            first_name="Service",
            last_name="Seller",
            national_id="9000000301",
            status=status,
        )
        cls.business = BusinessProfile.objects.create(
            vendor=cls.vendor,
            business_name="Service Seller",
            display_name="Service Seller",
        )
        cls.other_vendor = Vendor.objects.create(
            phone="+989120000302",
            first_name="Other",
            last_name="Seller",
            national_id="9000000302",
            status=status,
        )
        cls.other_business = BusinessProfile.objects.create(
            vendor=cls.other_vendor,
            business_name="Other Seller",
            display_name="Other Seller",
        )
        cls.no_business_vendor = Vendor.objects.create(
            phone="+989120000303",
            first_name="No",
            last_name="Business",
            national_id="9000000303",
            status=status,
        )

    def setUp(self):
        self.authenticate(self.vendor)

    def authenticate(self, vendor):
        token = RefreshToken.for_user(vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def make_configuration(self, business=None, mode=None, **overrides):
        return BusinessProfileServiceMode.objects.create(
            business_profile=business or self.business,
            service_mode=mode or self.online,
            **overrides,
        )

    def test_requires_authentication(self):
        self.client.credentials()

        self.assertEqual(
            self.client.get("/api/vendor/business/service-modes").status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/vendor/business/service-modes",
                {"service_mode_id": self.online.id},
                format="json",
            ).status_code,
            401,
        )

    def test_options_expose_only_active_modes(self):
        self.in_person.is_active = False
        self.in_person.save()

        response = self.client.get("/api/vendor/business/service-modes/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["code"] for row in response.data["data"]], ["online"]
        )

    def test_lists_only_the_callers_configurations(self):
        own = self.make_configuration(self.business, self.online)
        self.make_configuration(self.other_business, self.in_person)

        response = self.client.get("/api/vendor/business/service-modes")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["data"]], [own.id])
        self.assertEqual(
            response.data["data"][0]["service_mode"]["code"], "online"
        )

    def test_lists_disabled_configurations_too(self):
        self.make_configuration(self.business, self.online, is_active=False)

        response = self.client.get("/api/vendor/business/service-modes")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"][0]["is_active"])

    def test_enables_a_mode(self):
        response = self.client.post(
            "/api/vendor/business/service-modes",
            {"service_mode_id": self.in_person.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(data["service_mode"]["code"], "in_person")
        self.assertTrue(data["is_active"])
        self.assertTrue(
            BusinessProfileServiceMode.objects.filter(
                business_profile=self.business, service_mode=self.in_person
            ).exists()
        )

    def test_duplicate_configuration_is_rejected(self):
        self.make_configuration(self.business, self.online)

        response = self.client.post(
            "/api/vendor/business/service-modes",
            {"service_mode_id": self.online.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("service_mode", response.data["errors"])

    def test_inactive_mode_is_rejected(self):
        self.in_person.is_active = False
        self.in_person.save()

        response = self.client.post(
            "/api/vendor/business/service-modes",
            {"service_mode_id": self.in_person.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("service_mode", response.data["errors"])
        self.assertFalse(
            BusinessProfileServiceMode.objects.filter(
                business_profile=self.business
            ).exists()
        )

    def test_unknown_mode_id_is_rejected(self):
        response = self.client.post(
            "/api/vendor/business/service-modes",
            {"service_mode_id": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("service_mode_id", response.data["errors"])

    def test_disables_a_configuration(self):
        configuration = self.make_configuration(self.business, self.online)

        response = self.client.patch(
            f"/api/vendor/business/service-modes/{configuration.id}",
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["is_active"])
        configuration.refresh_from_db()
        self.assertFalse(configuration.is_active)

    def test_enables_a_disabled_configuration(self):
        configuration = self.make_configuration(
            self.business, self.online, is_active=False
        )

        response = self.client.patch(
            f"/api/vendor/business/service-modes/{configuration.id}",
            {"is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["is_active"])

    def test_cannot_reenable_a_globally_inactive_mode(self):
        configuration = self.make_configuration(
            self.business, self.online, is_active=False
        )
        self.online.is_active = False
        self.online.save()

        response = self.client.patch(
            f"/api/vendor/business/service-modes/{configuration.id}",
            {"is_active": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("service_mode", response.data["errors"])
        configuration.refresh_from_db()
        self.assertFalse(configuration.is_active)

    def test_another_business_configuration_is_not_reachable(self):
        other = self.make_configuration(self.other_business, self.online)

        self.assertEqual(
            self.client.get(
                f"/api/vendor/business/service-modes/{other.id}"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/vendor/business/service-modes/{other.id}",
                {"is_active": False},
                format="json",
            ).status_code,
            404,
        )
        other.refresh_from_db()
        self.assertTrue(other.is_active)

    def test_a_vendor_without_a_business_gets_an_empty_list(self):
        self.authenticate(self.no_business_vendor)

        self.assertEqual(
            self.client.get("/api/vendor/business/service-modes").data["data"],
            [],
        )
        response = self.client.post(
            "/api/vendor/business/service-modes",
            {"service_mode_id": self.online.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
