from django.db import models

from .base import ImmutableCodeModel


class ShipmentPricingMethod(ImmutableCodeModel):
    """A platform-wide way to price a shipment.

    The row says a pricing method is available. It does not say the
    calculation exists: that belongs to ``ShipmentPricingService``, which
    keeps its own implementation registry so a future row cannot silently
    become usable before its calculator is written.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipment_pricing_method"
        ordering = ["id"]

    def __str__(self):
        return self.code
