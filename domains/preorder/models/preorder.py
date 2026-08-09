from django.db import models


class PreOrder(models.Model):
    class Meta:
        db_table = "preorder"
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product"],
                name="preorder_customer_product_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="preorder_customer_created_idx",
            ),
            models.Index(
                fields=["product"],
                name="preorder_product_idx",
            ),
        ]

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.CASCADE,
        related_name="pre_orders",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="pre_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer} -> {self.product.name}"