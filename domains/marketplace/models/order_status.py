from django.db import models


class MarketplaceOrderStatus(models.Model):
    """Status vocabulary for marketplace orders.

    Seeded from the same constants as the shop vocabulary, so both flows
    speak the same words while staying free to reach different statuses.
    """

    class Meta:
        db_table = "marketplace_order_status"
        ordering = ["id"]

    name = models.CharField(max_length=50, unique=True)
    fa_name = models.CharField(max_length=50)
    description = models.TextField(blank=True, default="")

    def __str__(self):
        return self.name
