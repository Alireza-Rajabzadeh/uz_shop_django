from django.db import models


class MarketplaceCart(models.Model):
    """A customer's marketplace basket.

    Deliberately carries no business: pricing is read live from each variant's
    offer at render time, and checkout decides each order's business from the
    offers it actually sold, which is what keeps ``MarketplaceOrder.business``
    and ``MarketplaceOrderItem.marketplace_offer`` consistent.
    """

    class Meta:
        db_table = "marketplace_cart"

    customer = models.OneToOneField(
        "customer.Customer",
        on_delete=models.CASCADE,
        related_name="marketplace_cart",
    )
    address_info = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Marketplace cart #{self.pk} ({self.customer})"
