from django.db import models


class InventorySupplyConsumption(models.Model):
    # COGS snapshot linking one sold order item to the specific supply cost
    # layer(s) it consumed. unit_cost snapshots the supply's landed unit cost
    # at consumption time so historical COGS never shifts with later edits.

    class Meta:
        db_table = "inventory_supply_consumption"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="inventory_supply_consumption_qty_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(total_cost=models.F("quantity") * models.F("unit_cost")),
                name="inventory_supply_consumption_total_matches",
            ),
            models.CheckConstraint(
                condition=models.Q(reversed_quantity__gte=0),
                name="inventory_supply_consumption_reversed_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(reversed_quantity__lte=models.F("quantity")),
                name="inventory_supply_consumption_reversed_lte_quantity",
            ),
            models.UniqueConstraint(
                fields=["order_item", "supply"],
                name="inventory_supply_consumption_order_supply_unique",
            ),
        ]

    supply = models.ForeignKey(
        "InventorySupply",
        on_delete=models.PROTECT,
        related_name="consumptions",
    )
    order_item = models.ForeignKey(
        "order.OrderItem",
        on_delete=models.PROTECT,
        related_name="supply_consumptions",
    )
    quantity = models.PositiveIntegerField()
    reversed_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=15, decimal_places=2)
    total_cost = models.DecimalField(max_digits=17, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.total_cost = (self.unit_cost * self.quantity).quantize(self.unit_cost)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_item_id} <- {self.supply_id} x{self.quantity}"
