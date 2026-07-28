
from django.db import models

class ProductVariantsDetails(models.Model):
    class Meta:
        db_table = "catalog_product_variants_details"
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "detail"],
                name="catalog_variant_detail_unique",
            ),
        ]

    variant = models.ForeignKey(
        "ProductVariants",
        on_delete=models.CASCADE,
        related_name="details"
    )
    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)

    value = models.CharField(max_length=250, blank=True)
    extra_value = models.CharField(max_length=250, blank=True , null=True)

    def __str__(self):
        return f"{self.variant}: {self.detail}"
