from django.db import models


class WarehouseStatus(models.Model):
    class Meta:
        db_table = "inventory_warehouse_status"

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
