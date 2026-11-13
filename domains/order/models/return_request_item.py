from django.db import models

from .return_request import ReturnRequest


class ReturnRequestItem(models.Model):
    class Meta:
        db_table = "shop_return_request_item"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="shop_return_item_quantity_gt_0",
            ),
            models.UniqueConstraint(
                fields=["return_request", "order_item"],
                name="shop_return_unique_order_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["order_item"],
                name="shop_ret_item_order_item_idx",
            ),
        ]

    return_request = models.ForeignKey(
        ReturnRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.ForeignKey(
        "order.OrderItem",
        on_delete=models.PROTECT,
        related_name="return_request_items",
    )
    quantity = models.PositiveIntegerField()
    reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Return item #{self.pk} for order item #{self.order_item_id}"
