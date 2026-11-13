from enum import Enum


class ShipmentMethodEnum(Enum):
    VENDOR_DELIVERY = 1
    POST = 2
    COURIER = 3
    CUSTOMER_PICKUP = 4

    @property
    def code(self) -> str:
        return {
            ShipmentMethodEnum.VENDOR_DELIVERY: "vendor_delivery",
            ShipmentMethodEnum.POST: "post",
            ShipmentMethodEnum.COURIER: "courier",
            ShipmentMethodEnum.CUSTOMER_PICKUP: "customer_pickup",
        }[self]
