from decimal import Decimal

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.business_service_modes import (
    BusinessServiceModeSeeder,
)
from core.management.seeders.shipment import ShipmentSeeder
from domains.business.models import (
    BusinessProfile,
    BusinessProfileServiceMode,
    BusinessShipment,
)
from domains.business.services import BusinessOnboardingService
from domains.vendor.models import Vendor, VendorStatus


class VendorBusinessOnboardingApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        BusinessServiceModeSeeder().run()
        ShipmentSeeder().run()

        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        cls.vendor = Vendor.objects.create(
            phone="+989120000401",
            first_name="Onboarding",
            last_name="Seller",
            national_id="9000000401",
            status=status,
        )

    def setUp(self):
        token = RefreshToken.for_user(self.vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def create_profile(self):
        return self.client.post(
            "/api/vendor/business/profile",
            {"business_name": "Onboarding Store", "display_name": "Onboarding Store"},
            format="json",
        )

    def test_profile_creation_initializes_service_mode_and_draft_shipment(self):
        response = self.create_profile()

        self.assertEqual(response.status_code, 201)
        business = BusinessProfile.objects.get(vendor=self.vendor)

        configuration = BusinessProfileServiceMode.objects.get(
            business_profile=business
        )
        self.assertEqual(configuration.service_mode.code, "online")
        self.assertTrue(configuration.is_active)

        shipment = BusinessShipment.objects.get(business=business)
        self.assertEqual(shipment.shipment_method.code, "vendor_delivery")
        self.assertEqual(shipment.pricing_method.code, "fixed")
        self.assertEqual(shipment.cost, Decimal("0.00"))
        self.assertFalse(shipment.is_active)
        self.assertFalse(shipment.is_default)

    def test_initialization_is_idempotent(self):
        self.create_profile()
        business = BusinessProfile.objects.get(vendor=self.vendor)

        BusinessOnboardingService.initialize(business)
        BusinessOnboardingService.initialize(business)

        self.assertEqual(
            BusinessProfileServiceMode.objects.filter(
                business_profile=business
            ).count(),
            1,
        )
        self.assertEqual(
            BusinessShipment.objects.filter(business=business).count(), 1
        )


class VendorBusinessOnboardingWithoutReferenceDataTests(APITestCase):
    """An unseeded environment must still allow a vendor to create a store."""

    @classmethod
    def setUpTestData(cls):
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        cls.vendor = Vendor.objects.create(
            phone="+989120000402",
            first_name="Unseeded",
            last_name="Seller",
            national_id="9000000402",
            status=status,
        )

    def setUp(self):
        token = RefreshToken.for_user(self.vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_profile_creation_skips_missing_reference_rows(self):
        response = self.client.post(
            "/api/vendor/business/profile",
            {"business_name": "Bare Store", "display_name": "Bare Store"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        business = BusinessProfile.objects.get(vendor=self.vendor)
        self.assertFalse(
            BusinessProfileServiceMode.objects.filter(
                business_profile=business
            ).exists()
        )
        self.assertFalse(BusinessShipment.objects.filter(business=business).exists())
