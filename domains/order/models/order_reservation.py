from django.db import models


class OrderItemReservation(models.Model):
    class Meta:
        db_table = "shop_order_item_reservation"
        indexes = [
            models.Index(
                fields=["inventory_type", "inventory_id"],
                name="shop_ord_resrv_invtry_idx",
            ),
            models.Index(
                fields=["linked_inventory"],
                name="shop_ord_resrv_new_inv_idx",
            ),
            models.Index(
                fields=["linked_unit"],
                name="shop_ord_resrv_new_unit_idx",
            ),
        ]

    order_item = models.ForeignKey(
        "OrderItem",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    inventory_type = models.CharField(max_length=32)
    inventory_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField(default=1)
    linked_inventory = models.ForeignKey(
        "inventory.Inventory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_reservations",
    )
    linked_unit = models.ForeignKey(
        "inventory.InventoryUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_reservations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inventory_type}#{self.inventory_id} x{self.quantity}"
