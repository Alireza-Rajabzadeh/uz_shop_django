from django.db import models

#     Defines how stock is handled for a product variant.
#     This is ONLY a configuration model, not business logic.

class InventoryStrategy(models.Model):

      code = models.CharField(max_length=50, unique=True)
      name = models.CharField(max_length=100)
      description = models.TextField(blank=True, null=True)

      class Meta:
        db_table = "inventory_strategies"
        indexes = [
            models.Index(fields=["code"]),
        ]

      def __str__(self):
        return self.name