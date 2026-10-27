from core.management.seeders.base import BaseSeeder
from domains.shipment.data.pricing_methods import SHIPMENT_PRICING_METHOD_SEED
from domains.shipment.data.shipment_methods import SHIPMENT_METHOD_SEED
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod


class ShipmentSeeder(BaseSeeder):
    """Idempotent seed for the shipping reference vocabularies.

    Both vocabularies are keyed on ``code`` — the contract other code reads.
    ``get_or_create`` with ``defaults`` means a re-run never duplicates a row
    and never overwrites an administrator's edits to a name, description, or
    activation setting. Rows are retired with ``is_active=False``, not deleted,
    because future shipment records will point at them.
    """

    def run(self):
        self._seed_shipment_methods()
        self._seed_pricing_methods()

    @staticmethod
    def _seed_shipment_methods():
        for row in SHIPMENT_METHOD_SEED:
            ShipmentMethod.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row.get("description"),
                    "is_active": row.get("is_active", True),
                },
            )

    @staticmethod
    def _seed_pricing_methods():
        for row in SHIPMENT_PRICING_METHOD_SEED:
            ShipmentPricingMethod.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row.get("description"),
                    "is_active": row.get("is_active", True),
                },
            )
