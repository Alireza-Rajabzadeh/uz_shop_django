from django.db import models


class Cart(models.Model):
    class Meta:
        db_table = "shop_cart"

    customer = models.OneToOneField(
        "customer.Customer",
        on_delete=models.CASCADE,
        related_name="cart",
    )
    address_info = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart #{self.pk} ({self.customer})"