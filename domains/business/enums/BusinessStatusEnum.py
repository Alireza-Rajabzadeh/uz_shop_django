from enum import Enum


class BusinessStatusEnum(Enum):
    """Lifecycle state of a business, decided by the admin.

    Values are fixed database ids: `business_status` reference rows are
    seeded with these ids, `BusinessProfile.status` defaults to
    `CONFIRMATION_AWAIT`, and the migration backfills pre-existing
    businesses to `ACTIVE`. The string `code` on the row is what the
    API contract exposes to the panels.
    """

    ACTIVE = 1
    BANNED = 2
    CONFIRMATION_AWAIT = 3
