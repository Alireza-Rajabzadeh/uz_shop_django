from enum import Enum


class VendorProductStatusEnum(Enum):
    DRAFT = 1
    CONFIRMATION_AWAIT = 2
    REQUEST_UPDATE = 3
    NEED_RECHECK = 4
    REJECT = 5
    CONFIRMED = 6

    @property
    def code(self) -> str:
        return self.name.lower()
