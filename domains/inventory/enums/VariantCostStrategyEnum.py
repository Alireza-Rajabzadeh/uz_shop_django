from enum import Enum


class VariantCostStrategyEnum(Enum):
    LATEST = "latest"
    WEIGHTED_AVERAGE = "weighted_average"
    FIFO_NEXT = "fifo_next"

    @classmethod
    def choices(cls):
        labels = {
            cls.LATEST: "Latest",
            cls.WEIGHTED_AVERAGE: "Weighted average",
            cls.FIFO_NEXT: "FIFO next",
        }
        return [(member.value, labels[member]) for member in cls]
