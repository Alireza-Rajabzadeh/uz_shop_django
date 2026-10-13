from core.management.seeders.base import BaseSeeder
from domains.business.data.business_statuses import BUSINESS_STATUS_SEED
from domains.business.models import BusinessStatus


class BusinessStatusSeeder(BaseSeeder):
    """Idempotent re-seed of the lifecycle reference rows.

    The migration already creates them; this converges databases where a
    row was removed and keeps `seed` the single entry point for
    reference data. Lookups are by `code` — the API contract — so fixed
    ids stay the migration's business.
    """

    def run(self):
        for record in BUSINESS_STATUS_SEED:
            BusinessStatus.objects.get_or_create(
                code=record["code"],
                defaults={"name": record["name"], "title": record["title"]},
            )
