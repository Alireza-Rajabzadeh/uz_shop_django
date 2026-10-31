from decimal import Decimal

from django.db import transaction

from domains.business.models import BusinessChargeCalculationType
from domains.business.services import BusinessShipmentService

from ..models import OrderCharge


class MarketplaceOrderChargeService:
    """Reads, calculates, and snapshots the charges of a marketplace order.

    Two different things are called a charge here, and both end up in
    ``marketplace_order_charge``:

    * a seller's configured ``BusinessCharge`` rows (tax / extra), calculated
      from the discounted subtotal, and
    * the shipment the customer chose, whose amount comes from the matching
      ``BusinessShipment`` configuration.

    ``calculate_order_charges`` is the read-only preview used by checkout's
    final step: it returns ``{shipment_charge, other_charges}`` and writes
    nothing. ``apply`` runs inside order creation and freezes the same values
    as rows, so a later edit or deletion of the configuration cannot move an
    existing order.

    ``apply`` still returns only the total of the non-shipment charges: the
    order keeps shipping in its own fields, and counting it in
    ``charges_total`` as well would double it.
    """

    TWO_PLACES = Decimal("0.01")
    HUNDRED = Decimal("100")

    @staticmethod
    def active_charges(business):
        return business.charges.filter(is_active=True).order_by("id")

    @classmethod
    def calculate_amount(cls, charge, discounted_subtotal):
        """The amount to store for one configured charge.

        Both operands are ``Decimal`` and the result is quantized like every
        other monetary value in the checkout flow.
        """
        if charge.calculation_type == BusinessChargeCalculationType.PERCENTAGE:
            amount = discounted_subtotal * charge.amount / cls.HUNDRED
        else:
            amount = charge.amount
        return amount.quantize(cls.TWO_PLACES)

    @classmethod
    def calculate_other_charges(cls, business, discounted_subtotal):
        """Describe every active configured charge without persisting it."""
        items = []
        total = Decimal("0.00")
        for charge in cls.active_charges(business):
            amount = cls.calculate_amount(charge, discounted_subtotal)
            items.append({
                "business_charge_id": charge.id,
                "name": charge.name,
                "type": charge.type,
                "calculation_type": charge.calculation_type,
                "rate": str(charge.amount),
                "amount": str(amount),
                "is_mandatory": charge.is_mandatory,
            })
            total += amount
        return {
            "total": str(total.quantize(cls.TWO_PLACES)),
            "items": items,
        }

    @classmethod
    def calculate_shipment_charge(cls, shipment):
        """Describe the chosen shipment configuration, or ``None``.

        The amount is the configured cost resolved through
        ``BusinessShipmentService`` so an inactive method cannot be priced.
        """
        if shipment is None:
            return None
        amount = BusinessShipmentService.calculate_price(shipment)
        return {
            "business_shipment_id": shipment.id,
            "shipment_method": {
                "id": shipment.shipment_method_id,
                "code": shipment.shipment_method.code,
                "name": shipment.shipment_method.name,
            },
            "name": shipment.shipment_method.name,
            "original_price": str(amount.quantize(cls.TWO_PLACES)),
            "amount": str(amount.quantize(cls.TWO_PLACES)),
        }

    @classmethod
    def calculate_order_charges(
        cls, business, discounted_subtotal, shipment=None
    ):
        """Return the checkout preview for shipment and other charges."""
        return {
            "shipment_charge": cls.calculate_shipment_charge(shipment),
            "other_charges": cls.calculate_other_charges(
                business, discounted_subtotal
            ),
        }

    @classmethod
    @transaction.atomic
    def apply(cls, order, discounted_subtotal, *, shipment=None, **kwargs):
        """Snapshot every charge onto ``order`` and return the other total.

        The caller's checkout transaction already wraps order creation, so a
        failure here rolls the order back with it. ``bulk_create`` keeps the
        rows atomic as a set rather than issuing one insert per charge.
        """
        rows = []
        total = Decimal("0.00")
        for charge in cls.active_charges(order.business):
            amount = cls.calculate_amount(charge, discounted_subtotal)
            rows.append(
                OrderCharge(
                    order=order,
                    business_charge=charge,
                    kind=OrderCharge.KIND_BUSINESS_CHARGE,
                    name=charge.name,
                    type=charge.type,
                    calculation_type=charge.calculation_type,
                    rate=charge.amount,
                    amount=amount,
                )
            )
            total += amount

        if shipment is not None:
            amount = BusinessShipmentService.calculate_price(shipment).quantize(
                cls.TWO_PLACES
            )
            rows.append(
                OrderCharge(
                    order=order,
                    business_shipment=shipment,
                    kind=OrderCharge.KIND_SHIPMENT,
                    name=shipment.shipment_method.name,
                    type=OrderCharge.KIND_SHIPMENT,
                    calculation_type="fixed",
                    rate=shipment.cost,
                    amount=amount,
                )
            )

        if rows:
            OrderCharge.objects.bulk_create(rows)
        return total.quantize(cls.TWO_PLACES)
