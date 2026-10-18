from core.management.seeders.base import BaseSeeder
from domains.vendors_club.data.activities import VENDOR_CLUB_ACTIVITY_SEED
from domains.vendors_club.data.transaction_types import (
    VENDOR_CLUB_TRANSACTION_TYPE_SEED,
)
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubPointTransactionType,
)


class VendorsClubSeeder(BaseSeeder):
    """Idempotent seed for the vendor club's predefined reference rows.

    Both vocabularies are keyed on ``code`` — the contract other code reads —
    so a fixed id stays the migration's business and re-running never
    duplicates. An existing row is left untouched: ``points`` and the display
    text are values an administrator may tune, and a re-seed must not undo
    that. Activities are retired by clearing ``is_active``, never deleted,
    because ledger rows point at the activity for the life of the program.
    """

    def run(self):
        self._seed_activities()
        self._seed_transaction_types()

    def _seed_activities(self):
        for row in VENDOR_CLUB_ACTIVITY_SEED:
            VendorClubActivity.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row["description"],
                    "points": row["points"],
                    "is_active": row.get("is_active", True),
                },
            )

    def _seed_transaction_types(self):
        for row in VENDOR_CLUB_TRANSACTION_TYPE_SEED:
            VendorClubPointTransactionType.objects.get_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "description": row["description"],
                },
            )
