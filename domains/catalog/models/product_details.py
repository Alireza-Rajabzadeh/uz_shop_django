
from django.db import models

class ProductDetails(models.Model):
    class Meta:
        db_table = "catalog_product_details"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "detail"],
                name="catalog_product_detail_unique",
            ),
        ]
        
    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="details"
    )

    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)

    value = models.CharField(max_length=250, blank=True)
    extra_value = models.CharField(max_length=250, blank=True , null=True)

    def __str__(self):
        return f"{self.product} - {self.detail}"
