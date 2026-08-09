from django.db import models


class Wishlist(models.Model):
    class Meta:
        db_table = "wishlist"
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product"],
                name="wishlist_customer_product_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="wishlist_customer_created_idx",
            ),
            models.Index(
                fields=["product"],
                name="wishlist_product_idx",
            ),
        ]

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer} -> {self.product.name}"