"""Initial reference rows for ``business.BusinessStatus``.

Pure data: no model imports, so both the migration that creates the
table and the ``seed`` command import it safely. Ids are fixed because
``BusinessProfile.status`` defaults to id 3 and the enum vocabulary
(``BusinessStatusEnum``) maps onto them.
"""

BUSINESS_STATUS_SEED = [
    {"id": 1, "code": "active", "name": "Active", "title": "فعال"},
    {"id": 2, "code": "banned", "name": "Banned", "title": "مسدود"},
    {
        "id": 3,
        "code": "confirmation_await",
        "name": "Confirmation await",
        "title": "در انتظار تایید",
    },
]
