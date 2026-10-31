from decimal import Decimal

from django.db import transaction

from domains.business.models import BusinessChargeCalculationType

from ..models import OrderCharge


class MarketplaceOrderChargeService:
    """Turns a business's active charges into order charge snapshots.

    Read the configuration, calculate each amount from the discounted
    subtotal, and write the rows the order keeps forever. Historical totals
    are read from ``OrderCharge.amount``; nothing here ever revisits a stored
    row after checkout, so a later edit or deletion of the source
    ``BusinessCharge`` cannot move an existing order.

    Shipping is deliberately absent: the shipment flow adds its own amount to
    the order total, and mixing it in here would count it twice.
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
    @transaction.atomic
    def apply(cls, order, discounted_subtotal):
        """Snapshot every active charge onto ``order`` and return the total.

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
                    name=charge.name,
                    type=charge.type,
                    calculation_type=charge.calculation_type,
                    rate=charge.amount,
                    amount=amount,
                )
            )
            total += amount
        if rows:
            OrderCharge.objects.bulk_create(rows)
        return total.quantize(cls.TWO_PLACES)
