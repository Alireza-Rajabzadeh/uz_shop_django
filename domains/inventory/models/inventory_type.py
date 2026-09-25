from django.db import models


class InventoryType(models.Model):
    class Meta:
        db_table = "inventory_inventory_type"
        ordering = ["id"]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name
