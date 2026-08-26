from django.db import models


class InventorySupply(models.Model):
    # Historical purchase/replenishment batch used as the foundation for
    # inventory costing. remaining_quantity is a costing concept only; it is
    # independent from inventory availability, sellable stock, reservations,
    # and SerializedStock state.

    class Meta:
        db_table = "inventory_supply"
        ordering = ["supplied_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="inventory_supply_quantity_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_quantity__gte=0),
                name="inventory_supply_remaining_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_quantity__lte=models.F("quantity")),
                name="inventory_supply_remaining_lte_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_buy_price__gte=0),
                name="inventory_supply_unit_buy_price_gte_zero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["variant", "warehouse", "supplied_at"],
                name="inv_supply_variant_wh_supplied",
            ),
        ]

    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="inventory_supplies",
    )
    warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="inventory_supplies",
    )
    quantity = models.PositiveIntegerField()
    remaining_quantity = models.PositiveIntegerField(null=True, blank=True)
    unit_buy_price = models.DecimalField(max_digits=15, decimal_places=2)
    supplied_at = models.DateTimeField()
    received_at = models.DateTimeField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self._state.adding and self.remaining_quantity is None:
            self.remaining_quantity = self.quantity
        super().save(*args, **kwargs)

    @property
    def is_received(self):
        return self.received_at is not None

    def __str__(self):
        return f"{self.variant.sku} @ {self.warehouse.code}: {self.quantity}"
