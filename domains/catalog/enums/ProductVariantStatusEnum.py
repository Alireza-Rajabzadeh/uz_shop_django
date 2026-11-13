from enum import Enum


class ProductVariantStatusEnum(Enum):
    ACTIVE = 1
    INACTIVE = 2
    PENDING = 3
    WAIT_FOR_ADMIN_CONFIRMATION = 4

    @property
    def code(self) -> str:
        return self.name.lower()
