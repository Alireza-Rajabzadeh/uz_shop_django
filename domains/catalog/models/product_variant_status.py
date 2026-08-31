from django.db import models


class ProductVariantStatus(models.Model):
    class Meta:
        db_table = "catalog_product_variant_status"

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
