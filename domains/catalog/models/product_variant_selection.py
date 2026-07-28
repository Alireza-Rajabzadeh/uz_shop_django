from django.db import models


class ProductVariantSelection(models.Model):
    class Meta:
        db_table = "catalog_product_variant_selection"
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "attribute"],
                name="catalog_variant_selection_attribute_unique",
            ),
            models.UniqueConstraint(
                fields=["variant", "option"],
                name="catalog_variant_selection_option_unique",
            ),
        ]

    variant = models.ForeignKey(
        "ProductVariants",
        on_delete=models.CASCADE,
        related_name="selections",
    )
    attribute = models.ForeignKey(
        "VariantAttribute",
        on_delete=models.PROTECT,
        related_name="variant_selections",
    )
    option = models.ForeignKey(
        "VariantOption",
        on_delete=models.PROTECT,
        related_name="variant_selections",
    )

    def __str__(self):
        return f"{self.variant}: {self.attribute} = {self.option}"
