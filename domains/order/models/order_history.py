from django.db import models


class OrderHistory(models.Model):
    order = models.ForeignKey(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="history",
    )
    action = models.ForeignKey(
        "order.OrderAction",
        on_delete=models.PROTECT,
        related_name="history_entries",
    )
    user_id = models.BigIntegerField(null=True, blank=True)
    user_model = models.CharField(max_length=100, null=True, blank=True)
    before_values = models.JSONField(default=dict)
    after_values = models.JSONField(default=dict)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "order_history"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["order", "-created_at"],
                name="ord_hist_order_created_idx",
            )
        ]

    def __str__(self):
        return f"Order #{self.order_id}: {self.action.code}"
