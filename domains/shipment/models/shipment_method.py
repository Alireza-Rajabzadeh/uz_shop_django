from django.db import models

from .base import ImmutableCodeModel


class ShipmentMethod(ImmutableCodeModel):
    """A platform-wide way an order can reach the customer.

    This is a catalogue, not an assignment: a business is not assumed to
    support every method. Per-business availability belongs to a later
    domain model, not to this reference table.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipment_method"
        ordering = ["id"]

    def __str__(self):
        return self.code
