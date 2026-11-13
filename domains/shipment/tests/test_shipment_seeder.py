from django.test import TestCase

from core.management.seeders.configs.shipment import ShipmentSeeder
from domains.shipment.data.pricing_methods import SHIPMENT_PRICING_METHOD_SEED
from domains.shipment.data.shipment_methods import SHIPMENT_METHOD_SEED
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod


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
