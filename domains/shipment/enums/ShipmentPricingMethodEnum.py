from enum import Enum


class ShipmentPricingMethodEnum(Enum):
    FIXED = 1

    @property
    def code(self) -> str:
        return "fixed"
