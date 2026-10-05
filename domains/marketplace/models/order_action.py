from django.db import models


class MarketplaceOrderAction(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    admin = models.BooleanField(default=False)
    customer = models.BooleanField(default=False)
    set_status = models.ForeignKey(
        "marketplace.MarketplaceOrderStatus",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="result_actions",
    )

    class Meta:
        db_table = "marketplace_order_action"
        ordering = ["id"]

    def __str__(self):
        return self.code


class MarketplaceOrderStatusAction(models.Model):
    order_status = models.ForeignKey(
        "marketplace.MarketplaceOrderStatus",
        on_delete=models.CASCADE,
        related_name="status_actions",
    )
    order_action = models.ForeignKey(
        MarketplaceOrderAction,
        on_delete=models.CASCADE,
        related_name="status_assignments",
    )

    class Meta:
        db_table = "marketplace_order_status_actions"
        ordering = ["order_status_id", "order_action_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order_status", "order_action"],
                name="marketplace_order_status_action_unique",
            )
        ]

    def __str__(self):
        return f"{self.order_status} -> {self.order_action}"
