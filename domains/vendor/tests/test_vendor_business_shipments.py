from decimal import Decimal

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.management.seeders.shipment import ShipmentSeeder
from domains.business.models import BusinessProfile, BusinessShipment
from domains.business.services import BusinessShipmentService
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod
from domains.vendor.models import Vendor, VendorStatus


class VendorBusinessShipmentApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        ShipmentSeeder().run()
        cls.fixed = ShipmentPricingMethod.objects.get(code="fixed")
        cls.post = ShipmentMethod.objects.get(code="post")
        cls.courier = ShipmentMethod.objects.get(code="courier")

        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active"}
        )
        cls.vendor = Vendor.objects.create(
            phone="+989120000201",
            first_name="Shipment",
            last_name="Seller",
            national_id="9000000201",
            status=status,
        )
        cls.business = BusinessProfile.objects.create(
            vendor=cls.vendor,
            business_name="Shipment Seller",
            display_name="Shipment Seller",
        )
        cls.other_vendor = Vendor.objects.create(
            phone="+989120000202",
            first_name="Other",
            last_name="Seller",
            national_id="9000000202",
            status=status,
        )
        cls.other_business = BusinessProfile.objects.create(
            vendor=cls.other_vendor,
            business_name="Other Seller",
            display_name="Other Seller",
        )

    def setUp(self):
        self.authenticate(self.vendor)

    def authenticate(self, vendor):
        token = RefreshToken.for_user(vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def payload(self, method=None, pricing=None, **overrides):
        values = {
            "shipment_method_id": (method or self.post).id,
            "pricing_method_id": (pricing or self.fixed).id,
            "cost": "100.00",
        }
        values.update(overrides)
        return values

    def make_shipment(self, business=None, method=None, **overrides):
        return BusinessShipment.objects.create(
            business=business or self.business,
            shipment_method=method or self.post,
            pricing_method=self.fixed,
            cost=Decimal("100.00"),
            **overrides,
        )

    def test_requires_authentication(self):
        self.client.credentials()

        self.assertEqual(
            self.client.get("/api/vendor/business/shipments").status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/vendor/business/shipments", self.payload(), format="json"
            ).status_code,
            401,
        )

    def test_lists_only_the_callers_configurations(self):
        own = self.make_shipment(self.business, self.post)
        self.make_shipment(self.other_business, self.courier)

        response = self.client.get("/api/vendor/business/shipments")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["data"]], [own.id])

    def test_creates_a_configuration(self):
        response = self.client.post(
            "/api/vendor/business/shipments",
            self.payload(is_default=True),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(data["shipment_method"]["code"], "post")
        self.assertEqual(data["pricing_method"]["code"], "fixed")
        self.assertEqual(data["cost"], "100.00")
        self.assertTrue(data["is_default"])
        self.assertTrue(data["is_active"])
        self.assertTrue(
            BusinessShipment.objects.filter(business=self.business).exists()
        )

    def test_duplicate_configuration_is_rejected(self):
        self.make_shipment(self.business, self.post)

        response = self.client.post(
            "/api/vendor/business/shipments", self.payload(), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("shipment_method", response.data["errors"])

    def test_inactive_shipment_method_is_rejected(self):
        self.post.is_active = False
        self.post.save()

        response = self.client.post(
            "/api/vendor/business/shipments", self.payload(), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("shipment_method", response.data["errors"])

    def test_inactive_pricing_method_is_rejected(self):
        self.fixed.is_active = False
        self.fixed.save()

        response = self.client.post(
            "/api/vendor/business/shipments", self.payload(), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pricing_method", response.data["errors"])

    def test_unsupported_pricing_method_is_rejected(self):
        weight = ShipmentPricingMethod.objects.create(
            code="weight", name="Weight"
        )

        response = self.client.post(
            "/api/vendor/business/shipments",
            self.payload(pricing=weight),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pricing_method", response.data["errors"])

    def test_negative_cost_is_rejected(self):
        response = self.client.post(
            "/api/vendor/business/shipments",
            self.payload(cost="-1.00"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("cost", response.data["errors"])

    def test_setting_a_new_default_clears_the_old_one(self):
        first = self.client.post(
            "/api/vendor/business/shipments",
            self.payload(method=self.post, is_default=True),
            format="json",
        )
        second = self.client.post(
            "/api/vendor/business/shipments",
            self.payload(method=self.courier, is_default=True),
            format="json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        first_row = BusinessShipment.objects.get(
            id=first.data["data"]["id"]
        )
        second_row = BusinessShipment.objects.get(
            id=second.data["data"]["id"]
        )
        self.assertFalse(first_row.is_default)
        self.assertTrue(second_row.is_default)

    def test_deactivating_a_default_clears_the_default(self):
        shipment = self.make_shipment(self.business, self.post, is_default=True)

        response = self.client.patch(
            f"/api/vendor/business/shipments/{shipment.id}",
            {"is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["is_active"])
        self.assertFalse(response.data["data"]["is_default"])

    def test_updates_pricing_configuration(self):
        shipment = self.make_shipment(self.business, self.post)

        response = self.client.patch(
            f"/api/vendor/business/shipments/{shipment.id}",
            {"cost": "250.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["cost"], "250.00")
        shipment.refresh_from_db()
        self.assertEqual(shipment.cost, Decimal("250.00"))

    def test_another_business_configuration_is_not_reachable(self):
        other = self.make_shipment(self.other_business, self.post)

        self.assertEqual(
            self.client.get(
                f"/api/vendor/business/shipments/{other.id}"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/vendor/business/shipments/{other.id}",
                {"cost": "1.00"},
                format="json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/vendor/business/shipments/{other.id}"
            ).status_code,
            404,
        )

    def test_deletes_own_configuration(self):
        shipment = self.make_shipment(self.business, self.post)

        response = self.client.delete(
            f"/api/vendor/business/shipments/{shipment.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BusinessShipment.objects.filter(id=shipment.id).exists()
        )

    def test_options_expose_only_selectable_methods(self):
        self.courier.is_active = False
        self.courier.save()
        ShipmentPricingMethod.objects.create(code="weight", name="Weight")
        ShipmentPricingMethod.objects.create(
            code="distance", name="Distance", is_active=False
        )

        response = self.client.get(
            "/api/vendor/business/shipments/options"
        )

        self.assertEqual(response.status_code, 200)
        method_codes = [
            row["code"] for row in response.data["data"]["shipment_methods"]
        ]
        self.assertIn("post", method_codes)
        self.assertNotIn("courier", method_codes)
        self.assertEqual(
            [row["code"] for row in response.data["data"]["pricing_methods"]],
            ["fixed"],
        )

    def test_a_vendor_without_a_business_gets_an_empty_list(self):
        vendor = Vendor.objects.create(
            phone="+989120000203",
            first_name="No",
            last_name="Business",
            national_id="9000000203",
            status=self.vendor.status,
        )
        self.authenticate(vendor)

        self.assertEqual(
            self.client.get("/api/vendor/business/shipments").data["data"], []
        )
        response = self.client.post(
            "/api/vendor/business/shipments", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
