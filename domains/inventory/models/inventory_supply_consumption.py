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
            models.UniqueConstraint(
                fields=["marketplace_order_item", "supply"],
                name="inventory_supply_consumption_mkt_supply_unique",
            ),
            # A consumption row belongs to exactly one sale. Exactly one is
            # required rather than at most one so a row can never describe
            # cost without saying what it was attributed to.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        order_item__isnull=False,
                        marketplace_order_item__isnull=True,
                    )
                    | models.Q(
                        order_item__isnull=True,
                        marketplace_order_item__isnull=False,
                    )
                ),
                name="inventory_supply_consumption_one_target",
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
        null=True,
        blank=True,
        related_name="supply_consumptions",
    )
    marketplace_order_item = models.ForeignKey(
        "marketplace.MarketplaceOrderItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
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
        target = self.order_item_id or self.marketplace_order_item_id
        return f"{target} <- {self.supply_id} x{self.quantity}"
