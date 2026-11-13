from django.db import models


class OrderAction(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    admin = models.BooleanField(default=False)
    customer = models.BooleanField(default=False)
    set_status = models.ForeignKey(
        "order.OrderStatus",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="result_actions",
    )

    class Meta:
        db_table = "order_actions"
        ordering = ["id"]

    def __str__(self):
        return self.code
