from core.management.seeders.base import BaseSeeder
from domains.business.data.business_service_modes import BUSINESS_SERVICE_MODE_SEED
from domains.business.models import BusinessServiceMode


class BusinessServiceModeSeeder(BaseSeeder):
    """Idempotent seed for the business service-mode vocabulary.

    Keyed on ``code`` — the contract other code reads — so a re-run never
    duplicates a row and never overwrites an administrator's edits to a name,
    description, or activation state. Retire a mode with ``is_active=False``;
    do not delete it, because business profiles will reference it.
    """

    def run(self):
        for row in BUSINESS_SERVICE_MODE_SEED:
            BusinessServiceMode.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row.get("description"),
                    "is_active": row.get("is_active", True),
                },
            )
