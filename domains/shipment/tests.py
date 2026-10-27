from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from core.management.seeders.shipment import ShipmentSeeder
from domains.shipment.data.pricing_methods import SHIPMENT_PRICING_METHOD_SEED
from domains.shipment.data.shipment_methods import SHIPMENT_METHOD_SEED
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod
from domains.shipment.services import (
    ShipmentCalculationService,
    ShipmentPricingService,
)


class ShipmentCalculationServiceTests(SimpleTestCase):
    def test_calculates_current_quote_for_cart_or_order_source(self):
        service = ShipmentCalculationService()

        for source in (object(), {"items": [], "address_info": {}}):
            with self.subTest(source=type(source).__name__):
                quote = service.calculate(source)
                self.assertEqual(quote.original_price, Decimal("200000.00"))
                self.assertEqual(quote.final_price, Decimal("0.00"))


class ShipmentMethodModelTests(TestCase):
    def test_can_be_created_and_retrieved(self):
        method = ShipmentMethod.objects.create(code="post", name="Post")

        self.assertEqual(ShipmentMethod.objects.get(code="post"), method)
        self.assertEqual(str(method), "post")
        self.assertIsNone(method.description)
        self.assertTrue(method.is_active)

    def test_code_is_unique(self):
        ShipmentMethod.objects.create(code="post", name="Post")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ShipmentMethod.objects.create(code="post", name="Duplicate")

    def test_code_cannot_be_changed(self):
        method = ShipmentMethod.objects.create(code="post", name="Post")
        method.code = "courier"

        with self.assertRaises(DjangoValidationError):
            method.save()


class ShipmentPricingMethodModelTests(TestCase):
    def test_code_is_unique(self):
        ShipmentPricingMethod.objects.create(code="fixed", name="Fixed Price")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ShipmentPricingMethod.objects.create(code="fixed", name="Duplicate")

    def test_code_cannot_be_changed(self):
        method = ShipmentPricingMethod.objects.create(
            code="fixed", name="Fixed Price"
        )
        method.code = "weight"

        with self.assertRaises(DjangoValidationError):
            method.save()


class ShipmentSeederTests(TestCase):
    def test_creates_the_expected_initial_records(self):
        ShipmentSeeder().run()

        self.assertEqual(
            set(ShipmentMethod.objects.values_list("code", flat=True)),
            {row["code"] for row in SHIPMENT_METHOD_SEED},
        )
        self.assertEqual(
            set(ShipmentPricingMethod.objects.values_list("code", flat=True)),
            {row["code"] for row in SHIPMENT_PRICING_METHOD_SEED},
        )

        fixed = ShipmentPricingMethod.objects.get(code="fixed")
        self.assertEqual(fixed.name, "Fixed Price")
        self.assertEqual(
            fixed.description,
            "A fixed shipping cost configured by the business.",
        )
        self.assertTrue(fixed.is_active)

    def test_repeated_runs_create_no_duplicates(self):
        ShipmentSeeder().run()
        before = (
            ShipmentMethod.objects.count(),
            ShipmentPricingMethod.objects.count(),
        )

        ShipmentSeeder().run()

        self.assertEqual(
            (
                ShipmentMethod.objects.count(),
                ShipmentPricingMethod.objects.count(),
            ),
            before,
        )
        self.assertEqual(
            ShipmentMethod.objects.count(), len(SHIPMENT_METHOD_SEED)
        )
        self.assertEqual(
            ShipmentPricingMethod.objects.count(),
            len(SHIPMENT_PRICING_METHOD_SEED),
        )

    def test_repeated_runs_preserve_admin_edits(self):
        ShipmentSeeder().run()

        method = ShipmentMethod.objects.get(code="post")
        method.name = "Custom post"
        method.description = "Edited by an administrator."
        method.is_active = False
        method.save()

        pricing = ShipmentPricingMethod.objects.get(code="fixed")
        pricing.name = "Custom fixed"
        pricing.description = None
        pricing.is_active = False
        pricing.save()

        ShipmentSeeder().run()

        method.refresh_from_db()
        pricing.refresh_from_db()
        self.assertEqual(method.name, "Custom post")
        self.assertEqual(method.description, "Edited by an administrator.")
        self.assertFalse(method.is_active)
        self.assertEqual(pricing.name, "Custom fixed")
        self.assertIsNone(pricing.description)
        self.assertFalse(pricing.is_active)


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
