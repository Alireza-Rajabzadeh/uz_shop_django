from django.db import models
from django.db.models import Q


class CartItem(models.Model):
    class Meta:
        db_table = "shop_cart_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="shop_cart_item_quantity_positive",
            ),
            models.UniqueConstraint(
                fields=["cart", "variant"],
                name="shop_cart_item_cart_variant_unique",
            ),
        ]

    cart = models.ForeignKey(
        "Cart",
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.quantity} x {self.variant.sku}"