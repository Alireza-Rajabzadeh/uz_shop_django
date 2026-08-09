from django.db import models


class OrderPaymentMethod(models.Model):
    class Meta:
        db_table = "shop_order_payment_method"
        ordering = ["id"]

    name = models.CharField(max_length=50, unique=True)
    fa_name = models.CharField(max_length=50)
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name