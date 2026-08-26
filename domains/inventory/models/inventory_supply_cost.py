from django.db import models

from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum


class InventorySupplyCost(models.Model):
    # An expense associated with a specific inventory supply batch that
    # contributes to its real acquisition/landed cost. Cost rows are pure
    # accounting records; they never touch stock, reservations, or the
    # supply's remaining_quantity.

    class Meta:
        db_table = "inventory_supply_cost"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="inventory_supply_cost_amount_gte_zero",
            ),
        ]

    supply = models.ForeignKey(
        "InventorySupply",
        on_delete=models.CASCADE,
        related_name="costs",
    )
    type = models.CharField(
        max_length=20,
        choices=InventorySupplyCostTypeEnum.choices(),
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.supply_id} {self.type}: {self.amount}"
