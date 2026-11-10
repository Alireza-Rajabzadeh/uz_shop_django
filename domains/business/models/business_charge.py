from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from .base import TimestampedModel
from .business_profile import BusinessProfile
from .choices import BusinessChargeCalculationType, BusinessChargeType


class BusinessCharge(TimestampedModel):
    """A fee one business adds on top of its prices.

    ``business`` cascades like the profile's other owned rows: deleting a
    business removes its charges with it instead of leaving an orphaned
    configuration behind. ``type`` separates the two current accounting
    meanings (``tax`` and ``extra``); ``calculation_type`` decides whether
    ``amount`` is an absolute value or a percentage of a later base. Only the
    vocabulary and validation live here — order calculations are deliberately
    out of scope, and no order flow reads these rows yet.

    Percentage charges are capped at 100, enforced both by the serializer and
    by the database so every caller is subject to the same rule.
    """

    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="charges",
    )
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=16, choices=BusinessChargeType.choices)
    calculation_type = models.CharField(
        max_length=16, choices=BusinessChargeCalculationType.choices
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=False)

    class Meta:
        db_table = "business_charges"
        ordering = ["id"]
        indexes = [
            models.Index(
                fields=["business", "is_active"],
                name="business_charge_active_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="business_charge_amount_gte_zero",
            ),
            models.CheckConstraint(
                condition=(
                    Q(calculation_type=BusinessChargeCalculationType.FIXED)
                    | Q(amount__lte=100)
                ),
                name="business_charge_percentage_lte_100",
            ),
        ]

    def __str__(self):
        return f"{self.business} → {self.name}"
