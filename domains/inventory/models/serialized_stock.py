from django.db import models


class SerializedStock(models.Model):
    class Meta:
        db_table = "inventory_serialized_stock"

    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="serialized_stocks",
    )
    warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="serialized_stocks",
    )
    serial_number = models.CharField(max_length=100, unique=True)
    sellable = models.BooleanField(default=True)
    reserved = models.BooleanField(default=False)
    status = models.ForeignKey(
        "SerializedStockStatus",
        on_delete=models.PROTECT,
        related_name="serialized_stocks",
    )

    def __str__(self):
        return f"{self.serial_number} ({self.status.name})"
