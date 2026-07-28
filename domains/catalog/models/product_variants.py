
from django.db import models
from core.constants import DISCOUNT_TYPES

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
        related_name="variants"
    )
    
    inventory_strategy = models.ForeignKey(
        "inventory.InventoryStrategy",
        on_delete=models.PROTECT
    )
    
    sku = models.CharField(max_length=255, unique=True)
    combination_key = models.CharField(max_length=500)
    price = models.DecimalField(max_digits=15, decimal_places=2, blank=True)

    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPES,
        blank=True,
        null=True,
    )

    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )
    
    def __str__(self):
        return self.sku or f"{self.product} #{self.pk}"
