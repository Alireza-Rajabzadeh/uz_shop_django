from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ImmutableCodeModel(TimestampedModel):
    """A reference record identified by a stable ``code``.

    Application logic keys off ``code``, never off a display name or a
    database id: ids are not portable between environments and names are
    editable. Mirrors `domains.packages.ImmutableCodeModel`, kept local so
    this domain does not depend on another domain's models.
    """

    code = models.CharField(max_length=50, unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored is not None and stored != self.code:
                raise ValidationError(
                    {"code": _("Code cannot be changed after creation.")}
                )
        super().save(*args, **kwargs)


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
