from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class ImmutableCodeModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            old_code = type(self).objects.filter(pk=self.pk).values_list(
                "code", flat=True
            ).first()
            if old_code is not None and old_code != self.code:
                raise ValueError("Code is immutable.")
        super().save(*args, **kwargs)


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
            from .online_payment_providers import provider_availability

            available, reason = provider_availability(self.payment_channel.code)
            if not available:
                raise ValidationError({"payment_method": reason})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BusinessPaymentStatus(models.Model):
    class Meta:
        db_table = "business_payment_status"
        verbose_name_plural = "business payment statuses"
        ordering = ["id"]

    name = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


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


class BusinessPaymentDocument(models.Model):
    payment = models.ForeignKey(
        BusinessPayment,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="business_payment_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "business_payment_document"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "file"],
                name="bp_payment_document_unique",
            ),
        ]

    def __str__(self):
        return f"Document for BusinessPayment #{self.payment_id}"
