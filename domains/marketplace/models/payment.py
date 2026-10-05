from django.db import models
from django.db.models import Q


class MarketplaceOrderPayment(models.Model):
    """A customer payment against a marketplace order.

    The whole payment vocabulary comes from the business side rather than the
    shop side: channel, method and status are the records a business
    configures, so a marketplace payment and a ``BusinessPayment`` always mean
    the same thing by "successful".
    """

    class Meta:
        db_table = "marketplace_order_payment"
        indexes = [
            models.Index(fields=["order"], name="mkt_ord_payment_order_idx"),
            models.Index(fields=["business"], name="mkt_ord_payment_bus_idx"),
            models.Index(
                fields=["business", "order", "status"],
                name="mkt_ord_pay_bus_ord_st_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="marketplace_order_payment_amount_positive",
            ),
        ]

    order = models.ForeignKey(
        "marketplace.MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.PROTECT,
        related_name="marketplace_order_payments",
    )
    payment_method = models.ForeignKey(
        "business_payments.BusinessPaymentMethod",
        on_delete=models.PROTECT,
        related_name="marketplace_payments",
    )
    payment_channel = models.ForeignKey(
        "business_payments.BusinessPaymentChannel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_payments",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    # One successful payment per order is enforced by a partial index created
    # in marketplace.0009: the successful status is a seeded row, so its id is
    # not known when this model is defined.
    status = models.ForeignKey(
        "business_payments.BusinessPaymentStatus",
        on_delete=models.PROTECT,
        related_name="marketplace_order_payments",
    )
    ref_number = models.CharField(max_length=128, null=True, blank=True)
    resource_account_number = models.CharField(max_length=64, null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Marketplace payment #{self.pk} ({self.payment_method}) - {self.status}"


class MarketplacePaymentDocument(models.Model):
    payment = models.ForeignKey(
        MarketplaceOrderPayment,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="marketplace_payment_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marketplace_payment_document"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "file"],
                name="marketplace_payment_document_unique",
            )
        ]

    def __str__(self):
        return f"Document for marketplace payment #{self.payment_id}"
