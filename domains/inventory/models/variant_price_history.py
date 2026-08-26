from django.db import models

from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
from domains.inventory.enums.VariantPriceHistorySourceEnum import (
    VariantPriceHistorySourceEnum,
)


class VariantPriceHistory(models.Model):
    class Meta:
        db_table = "inventory_variant_price_history"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(old_price__gte=0),
                name="inventory_price_history_old_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(new_price__gte=0),
                name="inventory_price_history_new_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(cost_basis__gte=0),
                name="inventory_price_history_cost_basis_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(expected_profit_percentage__gte=0),
                name="inventory_price_history_profit_gte_zero",
            ),
        ]

    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="price_history",
    )
    old_price = models.DecimalField(max_digits=15, decimal_places=2)
    new_price = models.DecimalField(max_digits=15, decimal_places=2)
    cost_basis = models.DecimalField(max_digits=17, decimal_places=2)
    cost_strategy = models.CharField(
        max_length=20,
        choices=VariantCostStrategyEnum.choices(),
    )
    expected_profit_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )
    source = models.CharField(
        max_length=20,
        choices=VariantPriceHistorySourceEnum.choices(),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.variant.sku}: {self.old_price} -> {self.new_price}"
