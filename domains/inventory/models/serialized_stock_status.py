from django.db import models


class SerializedStockStatus(models.Model):
    class Meta:
        db_table = "inventory_serialized_stock_status"

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
