from django.db import models
from django.db.models import Q


class OrderCharge(models.Model):
    """One configured charge applied to a marketplace order.

    Every value is snapshotted at checkout. ``business_charge`` is a nullable
    traceability pointer only: the row keeps its own name, type, calculation
    type, rate and calculated amount, so changing or deleting the original
    ``BusinessCharge`` never alters a historical order. Order totals are read
    from ``amount`` here, never recalculated from the pointer's target.

    The pointer uses ``SET_NULL`` so removing a configuration retires the link
    without touching the order row.
    """

    class Meta:
        db_table = "marketplace_order_charge"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["order"], name="mkt_order_charge_order_idx"),
            models.Index(
                fields=["business_charge"],
                name="mkt_order_charge_biz_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="marketplace_order_charge_amount_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(rate__gte=0),
                name="marketplace_order_charge_rate_gte_zero",
            ),
        ]

    order = models.ForeignKey(
        "marketplace.MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="charges",
    )
    business_charge = models.ForeignKey(
        "business.BusinessCharge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_order_charges",
    )
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=16)
    calculation_type = models.CharField(max_length=16)
    rate = models.DecimalField(max_digits=12, decimal_places=4)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.amount})"
