from enum import Enum


class ProductStatusEnum(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    PREORDER = "preorder"
