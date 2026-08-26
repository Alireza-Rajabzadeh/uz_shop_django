from django.db import models

from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum


class VariantPricing(models.Model):
    # Per-variant pricing configuration: the expected profit margin and the
    # cost-basis strategy used later to derive a suggested selling price.
    # This model stores configuration only; price calculations live in the
    # costing services and are never persisted here.

    class Meta:
        db_table = "inventory_variant_pricing"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expected_profit_percentage__gte=0),
                name="inventory_variant_pricing_profit_gte_zero",
            ),
        ]

    variant = models.OneToOneField(
        "catalog.ProductVariants",
        on_delete=models.CASCADE,
        related_name="pricing",
    )
    expected_profit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    cost_strategy = models.CharField(
        max_length=20,
        choices=VariantCostStrategyEnum.choices(),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.variant.sku}: {self.cost_strategy} +{self.expected_profit_percentage}%"
