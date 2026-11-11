from django.db import models

from .base import ImmutableCodeModel


class BusinessPaymentChannel(ImmutableCodeModel):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="business_payment_channels",
    )
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100, blank=True, default="")
    account_number = models.CharField(max_length=50, null=True, blank=True)
    card_number = models.CharField(max_length=30, null=True, blank=True)
    owner_name = models.CharField(max_length=150, null=True, blank=True)
    bank = models.ForeignKey(
        "banks.Bank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_payment_channels",
    )
    extra_data = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    logo_file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_payment_channel_logos",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_payment_channel"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"],
                name="bpc_business_code_unique",
            ),
        ]

    def __str__(self):
        return self.name
