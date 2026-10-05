from django.db import models
from django.db.models import Q


class MarketplaceOrderItem(models.Model):
    """One line of a marketplace order, priced as it was at checkout.

    ``marketplace_offer`` is a snapshot pointer rather than a live price: the
    offer may be repriced or deactivated afterwards, and historical totals
    must never be recomputed from it. ``variant_info`` carries the product
    detail the line was sold with, so the order still describes itself if the
    variant is later edited or removed.
    """

    class Meta:
        db_table = "marketplace_order_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="marketplace_order_item_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["order"], name="mkt_ord_item_order_idx"),
            models.Index(
                fields=["marketplace_offer"], name="mkt_ord_item_offer_idx"
            ),
        ]

    order = models.ForeignKey(
        "marketplace.MarketplaceOrder",
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="marketplace_order_items",
    )
    marketplace_offer = models.ForeignKey(
        "marketplace.BusinessOffer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="marketplace_order_items",
    )
    sku = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    discount_type = models.CharField(max_length=20, null=True, blank=True)
    discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    final_price = models.DecimalField(max_digits=15, decimal_places=2)
    variant_info = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sku} x{self.quantity}"
