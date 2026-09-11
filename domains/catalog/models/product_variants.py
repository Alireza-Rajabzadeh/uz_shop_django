
from django.db import models


class ProductVariants(models.Model):
    class Meta:
        db_table = "catalog_product_variants"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "combination_key"],
                name="catalog_product_variant_combination_unique",
            ),
        ]

    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="variants",
    )

    status = models.ForeignKey(
        "ProductVariantStatus",
        on_delete=models.PROTECT,
        related_name="variants",
        null=True,
        blank=True,
    )

    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.PROTECT,
        related_name="variants",
        null=True,
        blank=True,
    )
    domain = models.CharField(max_length=255, blank=True)

    sku = models.CharField(max_length=255, unique=True)
    combination_key = models.CharField(max_length=500)

    def __str__(self):
        return self.sku or f"{self.product} #{self.pk}"
