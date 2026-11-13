from django.db import models
from django.db.models import Q

from .payment_channel import PaymentChannel
from .payment_method import PaymentMethod


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(
        "order.Order", on_delete=models.CASCADE, related_name="payments"
    )
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name="payments"
    )
    payment_channel = models.ForeignKey(
        PaymentChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    ref_number = models.CharField(max_length=128, null=True, blank=True)
    resource_account_number = models.CharField(max_length=64, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_order_payment"
        indexes = [models.Index(fields=["order"], name="shop_order_payment_order_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="shop_payment_amount_positive"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "successful", "failed"]),
                name="shop_payment_status_valid",
            ),
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="successful"),
                name="shop_payment_one_successful_order",
            ),
        ]

    def __str__(self):
        return f"Payment #{self.pk} ({self.payment_method}) - {self.status}"
