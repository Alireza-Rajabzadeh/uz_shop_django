from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.management.seeders.business_service_modes import (
    BusinessServiceModeSeeder,
)
from domains.business.data.business_service_modes import BUSINESS_SERVICE_MODE_SEED
from domains.business.models import BusinessServiceMode


class BusinessServiceModeSeederTests(TestCase):
    def test_creates_the_expected_initial_records(self):
        BusinessServiceModeSeeder().run()

        self.assertEqual(
            set(BusinessServiceMode.objects.values_list("code", flat=True)),
            {row["code"] for row in BUSINESS_SERVICE_MODE_SEED},
        )

        online = BusinessServiceMode.objects.get(code="online")
        self.assertEqual(online.name, "Online")
        self.assertIsNotNone(online.description)
        self.assertTrue(online.is_active)

        in_person = BusinessServiceMode.objects.get(code="in_person")
        self.assertEqual(in_person.name, "In Person")
        self.assertTrue(in_person.is_active)

    def test_repeated_runs_create_no_duplicates(self):
        BusinessServiceModeSeeder().run()
        before = BusinessServiceMode.objects.count()

        BusinessServiceModeSeeder().run()

        self.assertEqual(BusinessServiceMode.objects.count(), before)
        self.assertEqual(before, len(BUSINESS_SERVICE_MODE_SEED))

    def test_repeated_runs_preserve_admin_edits(self):
        BusinessServiceModeSeeder().run()

        mode = BusinessServiceMode.objects.get(code="in_person")
        mode.name = "On site"
        mode.description = "Edited by an administrator."
        mode.is_active = False
        mode.save()

        BusinessServiceModeSeeder().run()

        mode.refresh_from_db()
        self.assertEqual(mode.name, "On site")
        self.assertEqual(mode.description, "Edited by an administrator.")
        self.assertFalse(mode.is_active)


class BusinessServiceModeModelTests(TestCase):
    def test_code_must_be_unique(self):
        BusinessServiceMode.objects.create(code="online", name="Online")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessServiceMode.objects.create(
                    code="online", name="Online again"
                )

    def test_code_cannot_be_changed_after_creation(self):
        mode = BusinessServiceMode.objects.create(code="online", name="Online")

        mode.code = "web"
        with self.assertRaises(ValidationError):
            mode.save()

        mode.refresh_from_db()
        self.assertEqual(mode.code, "online")
