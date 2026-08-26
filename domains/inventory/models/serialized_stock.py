from django.db import models
from django.db.models.functions import Lower


class SerializedStock(models.Model):
    class Meta:
        db_table = "inventory_serialized_stock"
        constraints = [
            models.UniqueConstraint(
                Lower("serial_number"),
                name="inventory_serial_number_ci_unique",
            ),
        ]

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
    serial_number = models.CharField(max_length=100)
    sellable = models.BooleanField(default=True)
    reserved = models.BooleanField(default=False)
    status = models.ForeignKey(
        "SerializedStockStatus",
        on_delete=models.PROTECT,
        related_name="serialized_stocks",
    )
    supply = models.ForeignKey(
        "InventorySupply",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="serialized_stocks",
    )

    def save(self, *args, **kwargs):
        self.serial_number = " ".join(self.serial_number.split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.serial_number} ({self.status.name})"
