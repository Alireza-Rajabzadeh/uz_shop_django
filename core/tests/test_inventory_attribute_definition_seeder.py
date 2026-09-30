from django.test import TestCase

from core.management.seeders.inventory_attribute_definitions import (
    InventoryAttributeDefinitionSeeder,
)
from domains.business.models import BusinessProfile
from domains.inventory.enums.InventoryAttributeDefinitionEnum import (
    InventoryAttributeDefinitionEnum,
)
from domains.inventory.models import InventoryAttributeDefinition


class InventoryAttributeDefinitionSeederTests(TestCase):
    """The global attribute vocabulary is shared reference data.

    Every seeded row must be global (``business IS NULL``) so the vendor list
    endpoint can offer it to every business, and a business-owned row with a
    seeded code must be adopted rather than duplicated: unit attributes keep
    referencing the same primary key.
    """

    def setUp(self):
        self.seeder = InventoryAttributeDefinitionSeeder()
        self.codes = set(InventoryAttributeDefinitionEnum.codes())

    def test_seeder_creates_every_global_definition(self):
        self.seeder.run()

        rows = InventoryAttributeDefinition.objects.filter(code__in=self.codes)
        self.assertEqual(rows.count(), len(self.codes))
        for row in rows:
            self.assertIsNone(row.business_id, f"{row.code} is not global")
            self.assertTrue(row.fa_title, f"{row.code} has no fa_title")
            self.assertTrue(row.name)

    def test_seeder_matches_the_enum(self):
        self.seeder.run()

        seeded = set(
            InventoryAttributeDefinition.objects.filter(
                business__isnull=True
            ).values_list("code", flat=True)
        )
        self.assertEqual(seeded, self.codes)
        self.assertIn("serial_number", seeded)
        self.assertIn("imei", seeded)

    def test_seeder_is_idempotent(self):
        self.seeder.run()
        first = list(
            InventoryAttributeDefinition.objects.order_by("id").values_list(
                "id", "business_id", "code"
            )
        )

        self.seeder.run()
        second = list(
            InventoryAttributeDefinition.objects.order_by("id").values_list(
                "id", "business_id", "code"
            )
        )

        self.assertEqual(first, second)
        self.assertEqual(
            InventoryAttributeDefinition.objects.filter(code__in=self.codes).count(),
            len(self.codes),
        )

    def _make_business_owned(self, code, name):
        """Return a business-owned row for ``code`` (the pre-seed two-state shape)."""
        business = BusinessProfile.objects.get(id=1)
        row = InventoryAttributeDefinition.objects.filter(code=code).first()
        if row is None:
            row = InventoryAttributeDefinition(
                business=business, code=code, name=name, type="text"
            )
        else:
            row.business = business
            row.name = name
        row.save()
        return row

    def test_seeder_adopts_a_business_owned_row_keeps_its_id(self):
        """A legacy business-owned ``serial_number`` becomes the global row."""
        legacy = self._make_business_owned("serial_number", name="Serial Number")
        original_pk = legacy.pk

        self.seeder.run()

        adopted = InventoryAttributeDefinition.objects.get(code="serial_number")
        self.assertEqual(adopted.pk, original_pk)
        self.assertIsNone(adopted.business_id)
        self.assertEqual(
            InventoryAttributeDefinition.objects.filter(
                code="serial_number"
            ).count(),
            1,
        )

    def test_seeder_fills_fa_title_on_an_existing_row(self):
        row = self._make_business_owned("imei", name="IMEI")
        row.fa_title = ""
        row.save()

        self.seeder.run()

        row = InventoryAttributeDefinition.objects.get(code="imei")
        self.assertIsNone(row.business_id)
        self.assertTrue(row.fa_title)

    def test_seeder_absorbs_a_business_owned_twin(self):
        """A business row created before seeding must not shadow the global row."""
        self.seeder.run()
        global_row = InventoryAttributeDefinition.objects.get(code="imei")
        business = BusinessProfile.objects.get(id=1)
        InventoryAttributeDefinition.objects.create(
            business=business,
            name="IMEI (mine)",
            code="imei",
            type="text",
        )

        self.seeder.run()

        rows = InventoryAttributeDefinition.objects.filter(code="imei")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().pk, global_row.pk)
        self.assertIsNone(rows.first().business_id)

    def test_seeder_creates_rows_for_codes_that_do_not_exist_yet(self):
        InventoryAttributeDefinition.objects.create(
            business=BusinessProfile.objects.get(id=1),
            name="Box Serial",
            code="box_serial",
            type="text",
        )

        self.seeder.run()

        self.assertTrue(
            InventoryAttributeDefinition.objects.filter(code="box_serial").exists()
        )
        self.assertEqual(
            InventoryAttributeDefinition.objects.filter(code__in=self.codes).count(),
            len(self.codes),
        )
