from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from .base import TimestampedModel
from .business_profile import BusinessProfile


class BusinessShipment(TimestampedModel):
    """A shipment method one business offers, with its pricing configuration.

    The business domain owns the per-business choice. The shipping domain owns
    the global method and pricing vocabularies, so both foreign keys PROTECT:
    a method that a business already configured is retired by clearing
    ``is_active``, never by deleting the row out from under the configuration.
    """

    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="shipments",
    )
    shipment_method = models.ForeignKey(
        "shipment.ShipmentMethod",
        on_delete=models.PROTECT,
        related_name="business_shipments",
    )
    pricing_method = models.ForeignKey(
        "shipment.ShipmentPricingMethod",
        on_delete=models.PROTECT,
        related_name="business_shipments",
    )
    cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "business_shipment"
        ordering = ["-is_default", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "shipment_method"],
                name="business_shipment_business_method_unique",
            ),
            # PostgreSQL partial unique index: at most one default per
            # business, while businesses with no default are unaffected.
            models.UniqueConstraint(
                fields=["business"],
                condition=Q(is_default=True),
                name="business_shipment_one_default_per_business",
            ),
            models.CheckConstraint(
                condition=Q(cost__gte=0),
                name="business_shipment_cost_gte_zero",
            ),
        ]

    def __str__(self):
        return f"{self.business} → {self.shipment_method.code}"
