from core.management.seeders.base import BaseSeeder
from domains.inventory.enums.InventoryAttributeDefinitionEnum import (
    InventoryAttributeDefinitionEnum,
)
from domains.inventory.enums.InventoryAttributeTypeEnum import InventoryAttributeTypeEnum
from domains.inventory.models import InventoryAttributeDefinition, InventoryUnitAttribute


class InventoryAttributeDefinitionSeeder(BaseSeeder):
    """Provision the global unit-attribute vocabulary.

    Global rows carry ``business IS NULL``. Reference data wins on re-runs:
    the row keeps its id (unit attributes reference it), and an existing
    business-owned row with the same code is adopted as the global row rather
    than duplicated, so ``resolve_definition`` keeps finding one row per code.
    """

    VALUES = {
        InventoryAttributeDefinitionEnum.SERIAL_NUMBER.value: {
            "name": "Serial Number",
            "fa_title": "شماره سریال",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.IMEI.value: {
            "name": "IMEI",
            "fa_title": "شماره IMEI",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.IMEI_SECOND.value: {
            "name": "IMEI 2",
            "fa_title": "IMEI دوم",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.BARCODE.value: {
            "name": "Barcode",
            "fa_title": "بارکد",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.MAC_ADDRESS.value: {
            "name": "MAC Address",
            "fa_title": "آدرس MAC",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.BATCH_NUMBER.value: {
            "name": "Batch Number",
            "fa_title": "شماره سری تولید",
            "type": InventoryAttributeTypeEnum.TEXT.value,
        },
        InventoryAttributeDefinitionEnum.WARRANTY_MONTHS.value: {
            "name": "Warranty (months)",
            "fa_title": "گارانتی (ماه)",
            "type": InventoryAttributeTypeEnum.INTEGER.value,
        },
        InventoryAttributeDefinitionEnum.MANUFACTURE_DATE.value: {
            "name": "Manufacture Date",
            "fa_title": "تاریخ تولید",
            "type": InventoryAttributeTypeEnum.DATE.value,
        },
    }

    def run(self):
        for code, defaults in self.VALUES.items():
            self._upsert_global(code, defaults)

    def _upsert_global(self, code, defaults):
        rows = list(
            InventoryAttributeDefinition.objects.filter(code=code).order_by(
                "business", "id"
            )
        )
        if not rows:
            InventoryAttributeDefinition.objects.create(business=None, code=code, **defaults)
            return

        # PostgreSQL sorts NULL last for ASC, so the global row would be
        # picked second; adopt it explicitly when one already exists.
        global_row = next((row for row in rows if row.business_id is None), None)
        keeper = global_row or rows[0]
        keeper.business = None
        keeper.name = defaults["name"]
        keeper.fa_title = defaults["fa_title"]
        keeper.type = defaults["type"]
        keeper.save()

        # A business-owned twin of a seeded code would shadow the global row
        # forever, so fold its unit attributes into the global row first.
        for twin in rows:
            if twin.pk == keeper.pk:
                continue
            self._absorb(twin, keeper)

    @staticmethod
    def _absorb(twin, keeper):
        for attr in InventoryUnitAttribute.objects.filter(attribute_definition=twin):
            duplicate = InventoryUnitAttribute.objects.filter(
                inventory_unit=attr.inventory_unit_id,
                attribute_definition=keeper,
            ).exists()
            if duplicate:
                attr.delete()
            else:
                # Queryset update on purpose: a migrated value may predate the
                # global definition's type and must not fail full_clean().
                InventoryUnitAttribute.objects.filter(pk=attr.pk).update(
                    attribute_definition=keeper
                )
        twin.delete()
