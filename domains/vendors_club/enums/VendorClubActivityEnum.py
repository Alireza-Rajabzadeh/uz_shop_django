from enum import Enum


class VendorClubActivityEnum(Enum):
    PROFILE_COMPLETED = 1
    BUSINESS_VERIFIED = 2
    PRODUCT_PUBLISHED = 3
    FIRST_ORDER = 4
    ORDER_DELIVERED = 5

    @property
    def code(self) -> str:
        return {
            VendorClubActivityEnum.PROFILE_COMPLETED: "profile.completed",
            VendorClubActivityEnum.BUSINESS_VERIFIED: "business.verified",
            VendorClubActivityEnum.PRODUCT_PUBLISHED: "product.published",
            VendorClubActivityEnum.FIRST_ORDER: "first.order",
            VendorClubActivityEnum.ORDER_DELIVERED: "order.delivered",
        }[self]
