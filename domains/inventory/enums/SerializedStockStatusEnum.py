from enum import Enum


class SerializedStockStatusEnum(Enum):
    IN_STOCK = 1
    SOLD = 2
    RETURNED = 3
    DAMAGED = 4
    LOST = 5
