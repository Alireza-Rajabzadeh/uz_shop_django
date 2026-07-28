from django.db import models


class Warehouse(models.Model):
    class Meta:
        db_table = "inventory_warehouse"
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="inventory_single_default_warehouse",
            ),
        ]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    city = models.ForeignKey(
        "location.City",
        on_delete=models.PROTECT,
        related_name="warehouses",
    )
    address = models.TextField()
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    phone_numbers = models.JSONField(default=list, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    status = models.ForeignKey(
        "WarehouseStatus",
        on_delete=models.PROTECT,
        related_name="warehouses",
    )

    def save(self, *args, **kwargs):
        if not self.code:
            last = Warehouse.objects.order_by("id").last()
            next_id = last.id + 1 if last else 1
            self.code = f"WH-{next_id:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"
