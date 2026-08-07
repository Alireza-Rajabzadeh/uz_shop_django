from django.db import models
from django.db.models.functions import Lower, Trim


class VariantAttribute(models.Model):
    class Meta:
        db_table = "catalog_variant_attribute"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_variant_attribute_normalized_name_unique",
            ),
        ]

    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class VariantOption(models.Model):
    class Meta:
        db_table = "catalog_variant_option"
        ordering = ["attribute__name", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                "attribute",
                Lower(Trim("name")),
                name="catalog_variant_option_normalized_name_unique",
            ),
            models.UniqueConstraint(
                Lower("sku_code"),
                name="catalog_variant_option_sku_code_ci_unique",
            ),
        ]

    attribute = models.ForeignKey(
        VariantAttribute,
        on_delete=models.CASCADE,
        related_name="options",
    )
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100, blank=True, null=True)
    info = models.CharField(max_length=100, blank=True, default="")
    sku_code = models.CharField(max_length=16)

    def __str__(self):
        return f"{self.attribute}: {self.name}"


class CategoryVariantAttribute(models.Model):
    class Meta:
        db_table = "catalog_category_variant_attribute"
        constraints = [
            models.UniqueConstraint(
                fields=["category", "attribute"],
                name="catalog_category_variant_attribute_unique",
            ),
        ]

    category = models.ForeignKey(
        "Category",
        on_delete=models.CASCADE,
        related_name="variant_attribute_assignments",
    )
    attribute = models.ForeignKey(
        VariantAttribute,
        on_delete=models.CASCADE,
        related_name="category_assignments",
    )

    def __str__(self):
        return f"{self.category}: {self.attribute}"
