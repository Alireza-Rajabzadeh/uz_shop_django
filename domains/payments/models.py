from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


class ImmutableCodeModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            old_code = type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
            if old_code is not None and old_code != self.code:
                raise ValueError("Code is immutable.")
        super().save(*args, **kwargs)


class PaymentMethod(ImmutableCodeModel):
    class ChannelField(models.TextChoices):
        CARD_NUMBER = "card_number", "Card number"
        ACCOUNT_NUMBER = "account_number", "Account number"
        OWNER_NAME = "owner_name", "Owner name"

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    icon_file = models.ForeignKey(
        "files.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_method_icons",
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
        db_table = "shop_order_payment_method"
        ordering = ["id"]

    def __str__(self):
        return self.name


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


class PaymentChannelSupportedMethod(models.Model):
    payment_channel = models.ForeignKey(
        PaymentChannel, on_delete=models.CASCADE, related_name="supported_methods"
    )
    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.CASCADE, related_name="supported_channels"
    )

    class Meta:
        db_table = "shop_order_payment_channel_support"
        constraints = [
            models.UniqueConstraint(
                fields=["payment_channel", "payment_method"],
                name="shop_payment_channel_support_unique",
            )
        ]

    def __str__(self):
        return f"{self.payment_channel} supports {self.payment_method}"

    def clean(self):
        if self.payment_method.code == "online" and self.payment_method.is_active:
            from .online_payment_providers import provider_availability

            available, reason = provider_availability(self.payment_channel.code)
            if not available:
                raise ValidationError({"payment_method": reason})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


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


class PaymentDocument(models.Model):
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.ForeignKey(
        "files.File", on_delete=models.PROTECT, related_name="payment_documents"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shop_payment_document"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "file"], name="shop_payment_document_unique"
            )
        ]
