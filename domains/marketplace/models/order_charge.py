from django.db import models
from django.db.models import Q


class OrderCharge(models.Model):
    """One charge snapshotted onto a marketplace order.

    Every value is snapshotted at checkout. The two nullable pointers —
    ``business_charge`` for a configured fee and ``business_shipment`` for
    the chosen delivery method — are traceability only: the row keeps its own
    name, type, calculation type, rate and calculated amount, so changing or
    deleting the source configuration never alters a historical order. Order
    totals are read from ``amount`` here, never recalculated from a pointer.

    ``kind`` separates a seller's configured charge from the shipment row.
    Both live in this table so the order screen can show one itemised
    breakdown, while ``MarketplaceOrder.charges_total`` keeps counting only
    the non-shipment rows (shipping has its own order fields and must not be
    counted twice).

    The pointers use ``SET_NULL`` so removing a configuration retires the link
    without touching the order row.
    """

    KIND_BUSINESS_CHARGE = "business_charge"
    KIND_SHIPMENT = "shipment"
    KIND_CHOICES = [
        (KIND_BUSINESS_CHARGE, "Business charge"),
        (KIND_SHIPMENT, "Shipment"),
    ]

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
    business_shipment = models.ForeignKey(
        "business.BusinessShipment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_order_charges",
    )
    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=KIND_BUSINESS_CHARGE,
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
