from enum import Enum


class VariantPriceHistorySourceEnum(Enum):
    INVENTORY_PRICING = "inventory_pricing"
    MANUAL = "manual"

    @classmethod
    def choices(cls):
        return [
            (cls.INVENTORY_PRICING.value, "Inventory pricing"),
            (cls.MANUAL.value, "Manual"),
        ]
