from django.db import models
from django.db.models import Q


class OrderItem(models.Model):
    class Meta:
        db_table = "shop_order_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="shop_order_item_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["order"], name="shop_order_item_order_idx"),
        ]

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )
    sku = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    discount_type = models.CharField(max_length=20, null=True, blank=True)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    final_price = models.DecimalField(max_digits=15, decimal_places=2)
    inventory_strategy = models.ForeignKey(
        "inventory.InventoryStrategy",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    variant_info = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sku} x{self.quantity}"