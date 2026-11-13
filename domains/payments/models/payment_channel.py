from django.db import models

from .immutable_code_model import ImmutableCodeModel


class PaymentChannel(ImmutableCodeModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100, blank=True, default="")
    account_number = models.CharField(max_length=50, null=True, blank=True)
    card_number = models.CharField(max_length=30, null=True, blank=True)
    owner_name = models.CharField(max_length=150, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    logo_file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_channel_logos",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shop_order_payment_channel"
        ordering = ["id"]

    def __str__(self):
        return self.name
