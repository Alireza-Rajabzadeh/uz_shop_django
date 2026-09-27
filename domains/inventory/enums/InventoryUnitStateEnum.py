from enum import Enum


class InventoryUnitStateEnum(Enum):
    IN_STOCK = "in_stock"
    RESERVED = "reserved"
    SOLD = "sold"
    RETURNED = "returned"
    DAMAGED = "damaged"
    LOST = "lost"
    FROZEN = "frozen"
    # Set when a serialized unit outlives its serialization: the unit is kept
    # for the audit trail but is never sellable and never participates in a
    # serialized snapshot. Rows are purged by `purge_changed_type_units`.
    CHANGED_TYPE = "changed_type"

    @classmethod
    def choices(cls):
        return [(member.value, member.name.replace("_", " ").capitalize()) for member in cls]


# States that make a variant behave as serialized.
LIVE_STATES = frozenset({
    InventoryUnitStateEnum.IN_STOCK.value,
    InventoryUnitStateEnum.RESERVED.value,
})

# States that are history: never edited, never deleted, never diffed.
HISTORICAL_STATES = frozenset({
    InventoryUnitStateEnum.SOLD.value,
    InventoryUnitStateEnum.RETURNED.value,
    InventoryUnitStateEnum.DAMAGED.value,
    InventoryUnitStateEnum.LOST.value,
    InventoryUnitStateEnum.FROZEN.value,
    InventoryUnitStateEnum.CHANGED_TYPE.value,
})
