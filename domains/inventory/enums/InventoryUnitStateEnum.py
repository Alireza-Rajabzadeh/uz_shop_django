from enum import Enum


class InventoryUnitStateEnum(Enum):
    IN_STOCK = "in_stock"
    RESERVED = "reserved"
    SOLD = "sold"
    RETURNED = "returned"
    DAMAGED = "damaged"
    LOST = "lost"

    @classmethod
    def choices(cls):
        return [(member.value, member.name.replace("_", " ").capitalize()) for member in cls]
