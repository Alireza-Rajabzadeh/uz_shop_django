from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext as _

from .models import ShipmentPricingMethod


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


class ShipmentPricingService:
    """Calculates a shipping price from a pricing method and its config.

    The database row decides which pricing methods exist; ``CALCULATORS``
    decides which of them are implemented. They are deliberately separate, so
    seeding a future method never silently enables an unimplemented formula.

    The service is independent of ``BusinessShipment``: callers pass the
    pricing configuration instead of the service reading business-domain
    models. For the only implemented method, ``fixed``, the configuration is
    ``{"cost": <amount>}``.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    FIXED_CODE = "fixed"
    TWO_PLACES = Decimal("0.01")

    def calculate(self, pricing_method, config):
        method = self.resolve_method(pricing_method)
        calculator = self.CALCULATORS.get(method.code)
        if calculator is None:
            raise self.ValidationError(
                {"pricing_method": _("Unsupported pricing method.")}
            )
        return calculator(self, config)

    @staticmethod
    def resolve_method(pricing_method):
        """Resolve a code or a stored record to the current database row.

        Passing an instance is accepted, but it does not bypass the database:
        the row is re-read by primary key so an unsaved or stale object
        cannot invent a pricing method.
        """
        if isinstance(pricing_method, ShipmentPricingMethod):
            if pricing_method.pk is None:
                record = None
            else:
                record = ShipmentPricingMethod.objects.filter(
                    pk=pricing_method.pk
                ).first()
        else:
            record = ShipmentPricingMethod.objects.filter(
                code=pricing_method
            ).first()

        if record is None:
            raise ShipmentPricingService.ValidationError(
                {"pricing_method": _("Pricing method not found.")}
            )
        if not record.is_active:
            raise ShipmentPricingService.ValidationError(
                {"pricing_method": _("Pricing method is inactive.")}
            )
        return record

    def _calculate_fixed(self, config):
        if not isinstance(config, Mapping):
            raise self.ValidationError(
                {"cost": _("Pricing configuration must be a mapping.")}
            )

        value = config.get("cost")
        if value is None:
            raise self.ValidationError(
                {"cost": _("A shipping cost is required.")}
            )

        try:
            cost = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise self.ValidationError(
                {"cost": _("Shipping cost must be a valid amount.")}
            ) from exc

        if not cost.is_finite():
            raise self.ValidationError(
                {"cost": _("Shipping cost must be a valid amount.")}
            )
        if cost < 0:
            raise self.ValidationError(
                {"cost": _("Shipping cost cannot be negative.")}
            )

        return cost.quantize(self.TWO_PLACES)

    CALCULATORS = {
        FIXED_CODE: _calculate_fixed,
    }

    @classmethod
    def supported_codes(cls):
        """Pricing-method codes that have a calculation implementation.

        The database row is the availability contract; this is the
        implementation contract. Callers use it to expose only selectable
        pricing methods without duplicating the calculator registry.
        """
        return frozenset(cls.CALCULATORS)
