from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from domains.shipment.models import ShipmentPricingMethod


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
