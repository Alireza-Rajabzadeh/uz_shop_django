from core.management.seeders.base import BaseSeeder
from domains.shipment.enums import ShipmentMethodEnum, ShipmentPricingMethodEnum
from domains.shipment.models import ShipmentMethod, ShipmentPricingMethod


class ShipmentSeeder(BaseSeeder):
    """Idempotent seed for the shipping reference vocabularies using Enums."""

    SHIPMENT_METHODS = {
        ShipmentMethodEnum.VENDOR_DELIVERY: {
            "name": "Vendor Delivery",
            "description": "The vendor delivers the order directly to the customer.",
            "is_active": True,
        },
        ShipmentMethodEnum.POST: {
            "name": "Post",
            "description": "Delivery through the postal service.",
            "is_active": True,
        },
        ShipmentMethodEnum.COURIER: {
            "name": "Courier",
            "description": "Delivery through a courier service.",
            "is_active": True,
        },
        ShipmentMethodEnum.CUSTOMER_PICKUP: {
            "name": "Customer Pickup",
            "description": "The customer collects the order from the vendor.",
            "is_active": True,
        },
    }

    PRICING_METHODS = {
        ShipmentPricingMethodEnum.FIXED: {
            "name": "Fixed Price",
            "description": "A fixed shipping cost configured by the business.",
            "is_active": True,
        },
    }

    def run(self):
        self._seed_shipment_methods()
        self._seed_pricing_methods()
        self.sync_sequences(ShipmentMethod, ShipmentPricingMethod)

    def _seed_shipment_methods(self):
        for method_enum, defaults in self.SHIPMENT_METHODS.items():
            ShipmentMethod.objects.update_or_create(
                id=method_enum.value,
                defaults={"code": method_enum.code, **defaults},
            )

    def _seed_pricing_methods(self):
        for pricing_enum, defaults in self.PRICING_METHODS.items():
            ShipmentPricingMethod.objects.update_or_create(
                id=pricing_enum.value,
                defaults={"code": pricing_enum.code, **defaults},
            )
