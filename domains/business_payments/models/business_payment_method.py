from django.db import models

from .base import ImmutableCodeModel


class BusinessPaymentMethod(ImmutableCodeModel):
    class ChannelField(models.TextChoices):
        CARD_NUMBER = "card_number", "Card number"
        ACCOUNT_NUMBER = "account_number", "Account number"
        OWNER_NAME = "owner_name", "Owner name"

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    icon_file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_payment_method_icons",
    )
    point_to_channel_field = models.CharField(
        max_length=32,
        choices=ChannelField.choices,
        null=True,
        blank=True,
    )
    requires_documents = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "business_payment_method"
        ordering = ["id"]

    def __str__(self):
        return self.name
