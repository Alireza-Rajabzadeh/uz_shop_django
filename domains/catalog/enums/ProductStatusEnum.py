from enum import Enum


class ProductStatusEnum(Enum):
    ACTIVE = 1
    INACTIVE = 2
    PENDING = 3
    PREORDER = 4

    @property
    def code(self) -> str:
        return self.name.lower()
