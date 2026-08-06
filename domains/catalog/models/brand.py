from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Lower, Trim


class Brand(models.Model):
    class Meta:
        db_table = "catalog_brand"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_brand_normalized_name_unique",
            ),
        ]
        indexes = [
            GinIndex(
                fields=["name"],
                name="catalog_brand_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    name = models.CharField(max_length=150)
    fa_name = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self):
        return self.name
