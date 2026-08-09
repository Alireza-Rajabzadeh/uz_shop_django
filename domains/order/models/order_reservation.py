from django.db import models


class OrderItemReservation(models.Model):
    class Meta:
        db_table = "shop_order_item_reservation"
        indexes = [
            models.Index(
                fields=["inventory_type", "inventory_id"],
                name="shop_ord_resrv_invtry_idx",
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.inventory_type}#{self.inventory_id} x{self.quantity}"