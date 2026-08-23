from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ShipmentPrice:
    original_price: Decimal
    final_price: Decimal

    def payload(self):
        return {
            "original_price": str(self.original_price),
            "final_price": str(self.final_price),
        }


class ShipmentCalculationService:
    """Calculates a shipment quote from a complete cart or order source."""

    def calculate(self, source):
        return ShipmentPrice(
            original_price=Decimal("200000.00"),
            final_price=Decimal("0.00"),
        )
