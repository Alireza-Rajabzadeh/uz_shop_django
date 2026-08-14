from django.db import models

from .order_status import OrderStatus


class Order(models.Model):
    class Meta:
        db_table = "shop_order"
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="shop_ord_customer_creat_idx",
            ),
            models.Index(
                fields=["status", "reservation_expires_at"],
                name="shop_ord_status_resrv_idx",
            ),
        ]

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.ForeignKey(
        OrderStatus,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    address_info = models.JSONField()
    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    successful_payment = models.OneToOneField(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_order",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.pk} ({self.customer})"
