from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from core.management.seeders.shipment import ShipmentSeeder
from domains.business.models import BusinessProfile, BusinessShipment
from domains.business.services import BusinessShipmentService
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod
from domains.shipment.services import ShipmentPricingService
from domains.vendor.models import Vendor, VendorStatus


class ShipmentFixture(TestCase):
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
            phone="+989120000101",
            first_name="Shipment",
            last_name="Owner",
            national_id="9000000101",
            status=status,
        )
        cls.business = BusinessProfile.objects.create(
            vendor=cls.vendor,
            business_name="Shipment Business",
            display_name="Shipment Business",
        )

    def make_shipment(self, method=None, **overrides):
        values = {
            "business": self.business,
            "shipment_method": method or self.post,
            "pricing_method": self.fixed,
            "cost": Decimal("100.00"),
        }
        values.update(overrides)
        return BusinessShipment.objects.create(**values)


class BusinessShipmentModelTests(ShipmentFixture):
    def test_business_can_configure_multiple_methods(self):
        first = self.make_shipment(self.post)
        second = self.make_shipment(self.courier)

        self.assertEqual(
            set(
                BusinessShipment.objects.filter(business=self.business)
                .values_list("id", flat=True)
            ),
            {first.id, second.id},
        )

    def test_duplicate_business_and_method_is_rejected(self):
        self.make_shipment(self.post)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_shipment(self.post)

    def test_pricing_method_is_a_database_relationship(self):
        shipment = self.make_shipment(self.post)

        self.assertEqual(shipment.pricing_method_id, self.fixed.id)
        self.assertEqual(shipment.pricing_method.code, "fixed")
        self.assertEqual(shipment.shipment_method.code, "post")

    def test_negative_cost_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_shipment(self.post, cost=Decimal("-0.01"))

    def test_only_one_default_per_business(self):
        self.make_shipment(self.post, is_default=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_shipment(self.courier, is_default=True)

    def test_global_methods_are_protected_from_deletion(self):
        self.make_shipment(self.post)

        with self.assertRaises(ProtectedError):
            self.post.delete()
        with self.assertRaises(ProtectedError):
            self.fixed.delete()


class BusinessShipmentServiceTests(ShipmentFixture):
    def test_creates_a_configuration_and_calculates_fixed_price(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="12345.67",
        )

        self.assertEqual(shipment.cost, Decimal("12345.67"))
        self.assertEqual(
            BusinessShipmentService.calculate_price(shipment),
            Decimal("12345.67"),
        )
        self.assertEqual(
            ShipmentPricingService().calculate(
                shipment.pricing_method, {"cost": shipment.cost}
            ),
            Decimal("12345.67"),
        )

    def test_duplicate_configuration_is_rejected(self):
        BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.create_shipment(
                self.business,
                shipment_method=self.post,
                pricing_method=self.fixed,
                cost="200.00",
            )

        self.assertIn("shipment_method", ctx.exception.errors)

    def test_inactive_shipment_method_cannot_be_configured(self):
        self.post.is_active = False
        self.post.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.create_shipment(
                self.business,
                shipment_method=self.post,
                pricing_method=self.fixed,
                cost="100.00",
            )

        self.assertIn("shipment_method", ctx.exception.errors)

    def test_inactive_pricing_method_cannot_be_configured(self):
        self.fixed.is_active = False
        self.fixed.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.create_shipment(
                self.business,
                shipment_method=self.post,
                pricing_method=self.fixed,
                cost="100.00",
            )

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_unsupported_pricing_method_cannot_be_configured(self):
        weight = ShipmentPricingMethod.objects.create(
            code="weight", name="Weight"
        )

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.create_shipment(
                self.business,
                shipment_method=self.post,
                pricing_method=weight,
                cost="100.00",
            )

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_negative_cost_is_rejected(self):
        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.create_shipment(
                self.business,
                shipment_method=self.post,
                pricing_method=self.fixed,
                cost="-1.00",
            )

        self.assertIn("cost", ctx.exception.errors)

    def test_new_default_clears_the_previous_default(self):
        first = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
            is_default=True,
        )
        second = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.courier,
            pricing_method=self.fixed,
            cost="200.00",
            is_default=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertEqual(
            BusinessShipmentService.default_shipment(self.business), second
        )

    def test_deactivating_default_clears_default(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
            is_default=True,
        )

        shipment = BusinessShipmentService.update_shipment(
            shipment, is_active=False
        )

        self.assertFalse(shipment.is_default)
        self.assertFalse(shipment.is_active)
        self.assertIsNone(
            BusinessShipmentService.default_shipment(self.business)
        )

    def test_inactive_configuration_cannot_be_default(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(
                shipment, is_default=True, is_active=False
            )

        self.assertIn("is_default", ctx.exception.errors)

    def test_inactive_configuration_is_not_available_for_orders(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        BusinessShipmentService.update_shipment(shipment, is_active=False)
        shipment.refresh_from_db()

        self.assertNotIn(
            shipment, BusinessShipmentService.available_shipments(self.business)
        )
        with self.assertRaises(BusinessShipmentService.ValidationError):
            BusinessShipmentService.calculate_price(shipment)

    def test_globally_inactive_method_is_not_available_for_orders(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        self.post.is_active = False
        self.post.save()
        shipment.refresh_from_db()

        self.assertNotIn(
            shipment, BusinessShipmentService.available_shipments(self.business)
        )
        with self.assertRaises(BusinessShipmentService.ValidationError):
            BusinessShipmentService.calculate_price(shipment)

    def test_update_rejects_moving_to_an_existing_method(self):
        BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        second = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.courier,
            pricing_method=self.fixed,
            cost="200.00",
        )

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(
                second, shipment_method=self.post
            )

        self.assertIn("shipment_method", ctx.exception.errors)

    def test_update_rejects_selecting_an_inactive_shipment_method(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        self.courier.is_active = False
        self.courier.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(
                shipment, shipment_method=self.courier
            )

        self.assertIn("shipment_method", ctx.exception.errors)

    def test_update_cost_rejects_an_inactive_pricing_method(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        self.fixed.is_active = False
        self.fixed.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(shipment, cost="200.00")

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_reactivating_requires_active_global_methods(self):
        shipment = BusinessShipmentService.create_shipment(
            self.business,
            shipment_method=self.post,
            pricing_method=self.fixed,
            cost="100.00",
        )
        shipment = BusinessShipmentService.update_shipment(
            shipment, is_active=False
        )
        self.post.is_active = False
        self.post.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(shipment, is_active=True)

        self.assertIn("shipment_method", ctx.exception.errors)

        self.post.is_active = True
        self.post.save()
        self.fixed.is_active = False
        self.fixed.save()

        with self.assertRaises(BusinessShipmentService.ValidationError) as ctx:
            BusinessShipmentService.update_shipment(shipment, is_active=True)

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_lookup_is_scoped_to_the_business(self):
        other_vendor = Vendor.objects.create(
            phone="+989120000102",
            first_name="Other",
            last_name="Owner",
            national_id="9000000102",
            status=self.vendor.status,
        )
        other_business = BusinessProfile.objects.create(
            vendor=other_vendor,
            business_name="Other Business",
            display_name="Other Business",
        )
        other = self.make_shipment(business=other_business)

        self.assertIsNone(
            BusinessShipmentService.get_shipment(self.business, other.id)
        )
