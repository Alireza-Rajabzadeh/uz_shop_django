from enum import Enum


class InventorySupplyCostTypeEnum(Enum):
    SHIPMENT = "shipment"
    CUSTOMS = "customs"
    INSURANCE = "insurance"
    TAX = "tax"
    COMMISSION = "commission"
    HANDLING = "handling"
    STORAGE = "storage"
    OTHER = "other"

    @classmethod
    def choices(cls):
        return [(member.value, member.name.capitalize()) for member in cls]
