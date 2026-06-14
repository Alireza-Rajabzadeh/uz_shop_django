
from django.db import models

class ProductDetails(models.Model):
    class Meta:
        db_table = "catalog_product_details"
        
    status = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="details_product"
    )

    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)

    value = models.CharField(max_length=250, blank=True)
    extra_value = models.CharField(max_length=250, blank=True , null=True)

    def __str__(self):
        return self.name