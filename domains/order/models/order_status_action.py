from django.db import models

from .order_action import OrderAction


class OrderStatusAction(models.Model):
    order_status = models.ForeignKey(
        "order.OrderStatus",
        on_delete=models.CASCADE,
        related_name="status_actions",
    )
    order_action = models.ForeignKey(
        OrderAction,
        on_delete=models.CASCADE,
        related_name="status_assignments",
    )

    class Meta:
        db_table = "order_status_actions"
        ordering = ["order_status_id", "order_action_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order_status", "order_action"],
                name="order_status_action_unique",
            )
        ]

    def __str__(self):
        return f"{self.order_status} -> {self.order_action}"
