from django.db import models

from .payment_method import OrderPaymentMethod


class OrderPaymentChannel(models.Model):
    class Meta:
        db_table = "shop_order_payment_channel"
        ordering = ["id"]

    name = models.CharField(max_length=100, unique=True)
    fa_name = models.CharField(max_length=100, blank=True, default="")
    account_number = models.CharField(max_length=50, null=True, blank=True)
    card_number = models.CharField(max_length=30, null=True, blank=True)
    owner_name = models.CharField(max_length=150, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OrderPaymentChannelSupportMethod(models.Model):
    class Meta:
        db_table = "shop_order_payment_channel_support"
        constraints = [
            models.UniqueConstraint(
                fields=["payment_channel", "payment_method"],
                name="shop_payment_channel_support_unique",
            ),
        ]

    payment_channel = models.ForeignKey(
        OrderPaymentChannel,
        on_delete=models.CASCADE,
        related_name="supported_methods",
    )
    payment_method = models.ForeignKey(
        OrderPaymentMethod,
        on_delete=models.CASCADE,
        related_name="supported_channels",
    )

    def __str__(self):
        return f"{self.payment_channel} supports {self.payment_method}"