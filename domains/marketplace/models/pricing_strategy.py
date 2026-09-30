from django.db import models


class PricingStrategy(models.Model):
    """System-defined cost-basis strategy used by ``BusinessOffer.cost_strategy``.

    Reference data only: vendors read this table through the pricing-strategy
    lookup endpoints and never write to it. Adding a strategy means adding a
    member to ``VariantCostStrategyEnum``, seeding a row here, and teaching
    ``InventoryPricingService._calculate_basis()`` the new formula — there is
    deliberately no admin or vendor write path.

    ``description`` holds a content-component document (the same
    ``{components: [{id, key, version, props}]}`` shape landing pages use) so
    the front ends can render a per-strategy user guide through their existing
    content registry.
    """

    class Meta:
        db_table = "marketplace_pricing_strategy"
        ordering = ["id"]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    description = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name
