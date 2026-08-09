from django.db import models


class OrderStatus(models.Model):
    class Meta:
        db_table = "shop_order_status"
        ordering = ["id"]

    name = models.CharField(max_length=50, unique=True)
    fa_name = models.CharField(max_length=50)

    def __str__(self):
        return self.name