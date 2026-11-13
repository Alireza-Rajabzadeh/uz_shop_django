from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from domains.shipment.models import ShipmentMethod


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
