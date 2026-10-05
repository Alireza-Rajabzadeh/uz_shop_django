from decimal import Decimal

from django.db import models


class MarketplaceOrder(models.Model):
    """One marketplace checkout against a single business.

    ``business`` is denormalized onto the row so a marketplace order never has
    to be resolved through its items or their offers to be listed, filtered or
    authorized.
    """

    class Meta:
        db_table = "marketplace_order"
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="mkt_ord_customer_creat_idx",
            ),
            models.Index(
                fields=["business", "-created_at"],
                name="mkt_ord_business_creat_idx",
            ),
            models.Index(
                fields=["status", "reservation_expires_at"],
                name="mkt_ord_status_resrv_idx",
            ),
        ]

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="marketplace_orders",
    )
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.PROTECT,
        related_name="marketplace_orders",
    )
    status = models.ForeignKey(
        "marketplace.MarketplaceOrderStatus",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    address_info = models.JSONField()
    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    shipping_original_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("200000.00")
    )
    shipping_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    successful_payment = models.OneToOneField(
        "marketplace.MarketplaceOrderPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_order",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Marketplace order #{self.pk} ({self.customer})"
