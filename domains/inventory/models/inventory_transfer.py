from django.db import models


class InventoryTransfer(models.Model):
    class Meta:
        db_table = "inventory_transfer"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["source_inventory"], name="invtransfer_source_idx"),
            models.Index(fields=["destination_inventory"], name="invtransfer_dest_idx"),
            models.Index(fields=["variant"], name="invtransfer_variant_idx"),
            models.Index(fields=["created_at"], name="invtransfer_created_idx"),
        ]

    source_inventory = models.ForeignKey(
        "Inventory",
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
    )
    destination_inventory = models.ForeignKey(
        "Inventory",
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="inventory_transfers",
    )
    quantity = models.PositiveIntegerField()
    unit_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"Transfer {self.variant.sku}: {self.quantity} units "
            f"#{self.source_inventory_id} -> #{self.destination_inventory_id}"
        )
