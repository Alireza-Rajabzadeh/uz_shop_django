from decimal import Decimal

from django.test import TestCase

from domains.shipment.models import ShipmentPricingMethod
from domains.shipment.services import ShipmentPricingService


class ShipmentPricingServiceTests(TestCase):
    def setUp(self):
        self.service = ShipmentPricingService()
        self.fixed = ShipmentPricingMethod.objects.create(
            code="fixed",
            name="Fixed Price",
            description="A fixed shipping cost configured by the business.",
        )

    def test_fixed_pricing_returns_the_configured_cost(self):
        self.assertEqual(
            self.service.calculate("fixed", {"cost": "125000.50"}),
            Decimal("125000.50"),
        )
        self.assertEqual(
            self.service.calculate("fixed", {"cost": Decimal("0.00")}),
            Decimal("0.00"),
        )

    def test_accepts_a_stored_pricing_method_record(self):
        self.assertEqual(
            self.service.calculate(self.fixed, {"cost": 50000}),
            Decimal("50000.00"),
        )

    def test_missing_pricing_method_is_rejected(self):
        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("weight", {"cost": "100"})

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_inactive_pricing_method_is_rejected(self):
        self.fixed.is_active = False
        self.fixed.save()

        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("fixed", {"cost": "100"})

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_unsaved_pricing_method_record_is_rejected(self):
        unsaved = ShipmentPricingMethod(code="fixed", name="Fixed Price")

        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate(unsaved, {"cost": "100"})

        self.assertIn("pricing_method", ctx.exception.errors)

    def test_negative_cost_is_rejected(self):
        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("fixed", {"cost": "-0.01"})

        self.assertIn("cost", ctx.exception.errors)

    def test_missing_cost_is_rejected(self):
        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("fixed", {})

        self.assertIn("cost", ctx.exception.errors)

    def test_invalid_cost_is_rejected(self):
        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("fixed", {"cost": "not-a-number"})

        self.assertIn("cost", ctx.exception.errors)

    def test_unsupported_pricing_method_is_rejected(self):
        ShipmentPricingMethod.objects.create(code="weight", name="Weight")

        with self.assertRaises(ShipmentPricingService.ValidationError) as ctx:
            self.service.calculate("weight", {"cost": "100"})

        self.assertIn("pricing_method", ctx.exception.errors)
