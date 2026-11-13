from core.management.seeders.base import BaseSeeder
from domains.vendors_club.enums import (
    VendorClubActivityEnum,
    VendorClubTransactionTypeEnum,
)
from domains.vendors_club.models import (
    VendorClubActivity,
    VendorClubPointTransactionType,
)


class VendorsClubSeeder(BaseSeeder):
    """Idempotent seed for the vendor club's predefined reference rows using Enums.

    Both vocabularies are keyed on ``code`` — the contract other code reads —
    so a fixed id stays the migration's business and re-running never
    duplicates. An existing row is left untouched: ``points`` and the display
    text are values an administrator may tune, and a re-seed must not undo
    that.
    """

    ACTIVITIES = {
        VendorClubActivityEnum.PROFILE_COMPLETED: {
            "name": "Complete profile",
            "description": "Vendor completed the required business profile information.",
            "points": 100,
            "is_active": True,
        },
        VendorClubActivityEnum.BUSINESS_VERIFIED: {
            "name": "Verified business",
            "description": "The business profile passed verification.",
            "points": 150,
            "is_active": True,
        },
        VendorClubActivityEnum.PRODUCT_PUBLISHED: {
            "name": "Publish a product",
            "description": "Vendor published a product to the catalog.",
            "points": 50,
            "is_active": True,
        },
        VendorClubActivityEnum.FIRST_ORDER: {
            "name": "First order",
            "description": "Vendor received their first order.",
            "points": 200,
            "is_active": True,
        },
        VendorClubActivityEnum.ORDER_DELIVERED: {
            "name": "Deliver an order",
            "description": "Vendor delivered an order to the customer.",
            "points": 25,
            "is_active": True,
        },
    }

    TRANSACTION_TYPES = {
        VendorClubTransactionTypeEnum.EARN: {
            "name": "Earn",
            "description": "Points added when a vendor completes an activity.",
        },
        VendorClubTransactionTypeEnum.SPEND: {
            "name": "Spend",
            "description": "Points removed when a vendor redeems a reward.",
        },
        VendorClubTransactionTypeEnum.ADJUSTMENT: {
            "name": "Adjustment",
            "description": "A manual correction that credits available points.",
        },
        VendorClubTransactionTypeEnum.REVERSAL: {
            "name": "Reversal",
            "description": "Points removed to undo an earlier award.",
        },
    }

    def run(self):
        self._seed_activities()
        self._seed_transaction_types()
        self.sync_sequences(VendorClubActivity, VendorClubPointTransactionType)

    def _seed_activities(self):
        for activity_enum, defaults in self.ACTIVITIES.items():
            activity = VendorClubActivity.objects.filter(code=activity_enum.code).first()
            if activity is None:
                if not VendorClubActivity.objects.filter(id=activity_enum.value).exists():
                    VendorClubActivity.objects.create(
                        id=activity_enum.value,
                        code=activity_enum.code,
                        **defaults,
                    )
                else:
                    VendorClubActivity.objects.create(
                        code=activity_enum.code,
                        **defaults,
                    )

    def _seed_transaction_types(self):
        for tx_enum, defaults in self.TRANSACTION_TYPES.items():
            tx_type = VendorClubPointTransactionType.objects.filter(code=tx_enum.code).first()
            if tx_type is None:
                if not VendorClubPointTransactionType.objects.filter(id=tx_enum.value).exists():
                    VendorClubPointTransactionType.objects.create(
                        id=tx_enum.value,
                        code=tx_enum.code,
                        **defaults,
                    )
                else:
                    VendorClubPointTransactionType.objects.create(
                        code=tx_enum.code,
                        **defaults,
                    )
