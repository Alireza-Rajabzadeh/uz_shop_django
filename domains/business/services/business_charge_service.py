from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _

from domains.business.models import BusinessCharge, BusinessChargeCalculationType


class BusinessChargeService:
    """Reads and writes one business's charges.

    Business ownership is always a parameter: the caller (the vendor view)
    resolves the business from the authenticated vendor, and every lookup is
    scoped to it, so a charge id from another business answers "not found"
    instead of leaking or mutating the row. Order calculations deliberately
    stay out of this service; it only persists the configuration.
    """

    PERCENTAGE_MAX = Decimal("100")

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def list_charges(business):
        return BusinessCharge.objects.filter(business=business).order_by("id")

    @staticmethod
    def get_charge(business, charge_id, *, lock=False):
        queryset = BusinessCharge.objects
        if lock:
            queryset = queryset.select_for_update()
        return queryset.filter(pk=charge_id, business=business).first()

    @classmethod
    def validate_amount(cls, calculation_type, amount):
        """The amount rule shared by the serializer and every write path."""
        if amount is None:
            return amount
        if amount < 0:
            raise cls.ValidationError(
                {"amount": [_("Amount cannot be negative.")]}
            )
        if (
            calculation_type == BusinessChargeCalculationType.PERCENTAGE
            and amount > cls.PERCENTAGE_MAX
        ):
            raise cls.ValidationError(
                {"amount": [_("Percentage amount cannot exceed 100.")]}
            )
        return amount

    @classmethod
    @transaction.atomic
    def create_charge(cls, business, **values):
        cls.validate_amount(values.get("calculation_type"), values.get("amount"))
        return BusinessCharge.objects.create(business=business, **values)

    @classmethod
    @transaction.atomic
    def update_charge(cls, charge, **values):
        calculation_type = values.get("calculation_type", charge.calculation_type)
        amount = values.get("amount", charge.amount)
        cls.validate_amount(calculation_type, amount)
        for field, value in values.items():
            setattr(charge, field, value)
        charge.save()
        return charge

    @classmethod
    @transaction.atomic
    def set_active(cls, charge, is_active):
        charge = BusinessCharge.objects.select_for_update().get(pk=charge.pk)
        if charge.is_active != is_active:
            charge.is_active = is_active
            charge.save(update_fields=["is_active", "updated_at"])
        return charge

    @classmethod
    @transaction.atomic
    def delete_charge(cls, charge):
        charge.delete()
