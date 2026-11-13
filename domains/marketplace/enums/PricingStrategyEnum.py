from enum import Enum


class PricingStrategyEnum(Enum):
    LATEST = 1
    WEIGHTED_AVERAGE = 2
    FIFO_NEXT = 3

    @property
    def code(self) -> str:
        return {
            PricingStrategyEnum.LATEST: "latest",
            PricingStrategyEnum.WEIGHTED_AVERAGE: "weighted_average",
            PricingStrategyEnum.FIFO_NEXT: "fifo_next",
        }[self]
