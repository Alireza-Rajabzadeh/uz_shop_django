from enum import Enum


class VendorClubTransactionTypeEnum(Enum):
    EARN = 1
    SPEND = 2
    ADJUSTMENT = 3
    REVERSAL = 4

    @property
    def code(self) -> str:
        return self.name.lower()
