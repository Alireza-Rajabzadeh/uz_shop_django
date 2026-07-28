from django.db import models


class WarehouseStock(models.Model):
    class Meta:
        db_table = "inventory_warehouse_stock"
        unique_together = ("variant", "warehouse")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(sellable__lte=models.F("quantity")),
                name="inventory_stock_sellable_lte_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved__lte=models.F("sellable")),
                name="inventory_stock_reserved_lte_sellable",
            ),
        ]

    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="warehouse_stocks",
    )
    warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="stocks",
    )
    quantity = models.PositiveIntegerField()
    sellable = models.PositiveIntegerField()
    reserved = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=0)

    @property
    def available(self):
        return self.sellable - self.reserved

    def __str__(self):
        return f"{self.variant.sku} @ {self.warehouse.code}: {self.available}"
