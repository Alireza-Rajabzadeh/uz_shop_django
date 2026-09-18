from enum import Enum


class ProductStatusEnum(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    PREORDER = "preorder"
    WAIT_FOR_ADMIN_CONFIRMATION = "wait_for_admin_confirmation"
    ADMIN_REJECTED = "admin_rejected"
