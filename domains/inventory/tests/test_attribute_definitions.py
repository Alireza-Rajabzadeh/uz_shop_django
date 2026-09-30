from django.test import TestCase

from domains.business.models import BusinessProfile
from domains.inventory.models import InventoryAttributeDefinition
from domains.inventory.services.inventory_attribute_service import (
    InventoryAttributeService,
)


class ResolveDefinitionTests(TestCase):
    """Definition lookups are two-scoped.

    Serialized stock flows resolve ``serial_number`` through
    ``resolve_definition`` instead of an arbitrary ``filter(code=...).first()``,
    so the caller's own row wins over the seeded global row and a database
    that was never seeded still resolves a legacy row.
    """

    def setUp(self):
        self.business = BusinessProfile.objects.get(id=1)
        # Migration 0022 seeds a legacy business-owned row; start from a clean
        # slate so each case controls the scope explicitly.
        InventoryAttributeDefinition.objects.filter(code="serial_number").delete()
        self.global_definition = InventoryAttributeDefinition.objects.create(
            business=None,
            name="Serial Number",
            fa_title="شماره سریال",
            code="serial_number",
            type="text",
        )

    def test_global_row_is_returned_when_the_business_owns_none(self):
        resolved = InventoryAttributeService.resolve_definition(
            "serial_number", self.business
        )

        self.assertEqual(resolved.pk, self.global_definition.pk)

    def test_own_row_wins_over_the_global_row(self):
        own = InventoryAttributeDefinition.objects.create(
            business=self.business,
            name="Serial Number (mine)",
            code="serial_number",
            type="text",
        )

        resolved = InventoryAttributeService.resolve_definition(
            "serial_number", self.business
        )

        self.assertEqual(resolved.pk, own.pk)

    def test_missing_code_returns_none(self):
        self.assertIsNone(
            InventoryAttributeService.resolve_definition("does_not_exist", self.business)
        )
        self.assertIsNone(InventoryAttributeService.resolve_definition("", self.business))

    def test_foreign_row_is_never_returned_for_writes(self):
        other = BusinessProfile.objects.create(
            id=2,
            business_name="Other Business",
            display_name="Other",
        )
        InventoryAttributeDefinition.objects.create(
            business=other,
            name="Foreign Only",
            code="foreign_only",
            type="text",
        )

        self.assertIsNone(
            InventoryAttributeService.resolve_definition(
                "foreign_only", self.business, fallback_to_any=False
            )
        )

    def test_unseeded_database_keeps_resolving_a_legacy_row(self):
        """Databases seeded before the global scope existed still resolve."""
        legacy = InventoryAttributeDefinition.objects.create(
            business=self.business,
            name="Legacy",
            code="legacy_attribute",
            type="text",
        )

        resolved = InventoryAttributeService.resolve_definition(
            "legacy_attribute"
        )

        self.assertEqual(resolved.pk, legacy.pk)


class ListDefinitionsTests(TestCase):
    """A vendor sees shared reference data plus its own rows only."""

    def setUp(self):
        self.business = BusinessProfile.objects.get(id=1)
        self.other_business = BusinessProfile.objects.create(
            id=2,
            business_name="Other Business",
            display_name="Other",
        )
        self.global_definition = InventoryAttributeDefinition.objects.create(
            business=None, name="IMEI", fa_title="شماره IMEI", code="imei", type="text"
        )
        self.own_definition = InventoryAttributeDefinition.objects.create(
            business=self.business,
            name="Box Serial",
            code="box_serial",
            type="text",
        )
        self.foreign_definition = InventoryAttributeDefinition.objects.create(
            business=self.other_business,
            name="Foreign",
            code="foreign_attribute",
            type="text",
        )

    def test_returns_global_and_own_rows_only(self):
        rows = InventoryAttributeService.list_definitions(self.business)
        codes = {row.code for row in rows}

        self.assertIn("imei", codes)
        self.assertIn("box_serial", codes)
        self.assertNotIn("foreign_attribute", codes)

    def test_global_rows_sort_first(self):
        rows = list(InventoryAttributeService.list_definitions(self.business))

        self.assertTrue(rows[0].is_global)

    def test_an_unowned_business_sees_only_the_global_rows(self):
        codes = {row.code for row in InventoryAttributeService.list_definitions(None)}

        self.assertIn("imei", codes)
        self.assertNotIn("box_serial", codes)
        self.assertNotIn("foreign_attribute", codes)
