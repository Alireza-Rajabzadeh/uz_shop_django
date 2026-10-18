"""Predefined rows for ``vendors_club.VendorClubPointTransactionType``.

Pure data: no model imports, so the migration that creates the table and the
``seed`` command can both import it safely.

``code`` mirrors ``VendorClubPointTransaction.TransactionType`` and is what the
ledger stores; the table only carries display text, and the ledger keeps its own
code snapshot so the audit trail never moves with this reference data.
``VENDORS_CLUB_TRANSACTION_TYPE_SEED`` and that enum are kept from drifting
apart by the domain's seeder tests.
"""

VENDOR_CLUB_TRANSACTION_TYPE_SEED = [
    {
        "code": "earn",
        "name": "Earn",
        "description": "Points added when a vendor completes an activity.",
    },
    {
        "code": "spend",
        "name": "Spend",
        "description": "Points removed when a vendor redeems a reward.",
    },
    {
        "code": "adjustment",
        "name": "Adjustment",
        "description": "A manual correction that credits available points.",
    },
    {
        "code": "reversal",
        "name": "Reversal",
        "description": "Points removed to undo an earlier award.",
    },
]
