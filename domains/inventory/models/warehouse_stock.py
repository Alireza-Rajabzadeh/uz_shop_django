from django.db import models


class WarehouseStock(models.Model):
    class Meta:
        db_table = "inventory_warehouse_stock"
        unique_together = ("variant", "warehouse")

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
