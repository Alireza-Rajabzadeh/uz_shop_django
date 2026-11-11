from django.db import models
from django.db.models import Q

from .business_payment_channel import BusinessPaymentChannel
from .business_payment_method import BusinessPaymentMethod
from .business_payment_status import BusinessPaymentStatus


class BusinessPayment(models.Model):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="business_payments",
    )
    order = models.ForeignKey(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="business_payments",
    )
    payment_method = models.ForeignKey(
        BusinessPaymentMethod,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_channel = models.ForeignKey(
        BusinessPaymentChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.ForeignKey(
        BusinessPaymentStatus,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    ref_number = models.CharField(max_length=128, null=True, blank=True)
    resource_account_number = models.CharField(max_length=64, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_payment"
        indexes = [
            models.Index(fields=["business"], name="bp_business_idx"),
            models.Index(fields=["order"], name="bp_order_idx"),
            models.Index(fields=["business", "order", "status"], name="bp_bus_order_st_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="bp_payment_amount_positive"
            ),
        ]

    def __str__(self):
        return f"BusinessPayment #{self.pk} ({self.payment_method}) - {self.status}"
