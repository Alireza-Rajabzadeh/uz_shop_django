from django.db import models

from .payment_channel import OrderPaymentChannel
from .payment_method import OrderPaymentMethod

PAYMENT_PENDING = "pending"
PAYMENT_SUCCESS = "success"
PAYMENT_FAILED = "failed"

PAYMENT_STATUS_CHOICES = (
    (PAYMENT_PENDING, "Pending"),
    (PAYMENT_SUCCESS, "Success"),
    (PAYMENT_FAILED, "Failed"),
)


class OrderPayment(models.Model):
    class Meta:
        db_table = "shop_order_payment"
        indexes = [
            models.Index(fields=["order"], name="shop_order_payment_order_idx"),
        ]

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    payment_method = models.ForeignKey(
        OrderPaymentMethod,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_channel = models.ForeignKey(
        OrderPaymentChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=16, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING)
    ref_number = models.CharField(max_length=128, null=True, blank=True)
    resource_account_number = models.CharField(max_length=64, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.pk} ({self.payment_method}) - {self.status}"