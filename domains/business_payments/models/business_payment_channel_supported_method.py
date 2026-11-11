from django.core.exceptions import ValidationError
from django.db import models

from .business_payment_channel import BusinessPaymentChannel
from .business_payment_method import BusinessPaymentMethod


class BusinessPaymentChannelSupportedMethod(models.Model):
    payment_channel = models.ForeignKey(
        BusinessPaymentChannel,
        on_delete=models.CASCADE,
        related_name="supported_methods",
    )
    payment_method = models.ForeignKey(
        BusinessPaymentMethod,
        on_delete=models.CASCADE,
        related_name="supported_channels",
    )

    class Meta:
        db_table = "business_payment_channel_support"
        constraints = [
            models.UniqueConstraint(
                fields=["payment_channel", "payment_method"],
                name="bpc_support_unique",
            ),
        ]

    def __str__(self):
        return f"{self.payment_channel} supports {self.payment_method}"

    def clean(self):
        if self.payment_method.code == "online" and self.payment_method.is_active:
            from ..online_payment_providers import provider_availability

            available, reason = provider_availability(self.payment_channel.code)
            if not available:
                raise ValidationError({"payment_method": reason})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
