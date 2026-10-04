
from django.conf import settings
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

    # Ownership and review state for vendor-created variants. A variant the
    # vendor creates starts in `wait_for_admin_confirmation`; only its creator
    # may reshape it while it waits, and no one may price or stock it until an
    # admin records `confirmed_by`.
    created_by_vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_variants",
    )
    creator_model = models.CharField(max_length=50, blank=True, default="")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_variants",
    )

    sku = models.CharField(max_length=255, unique=True)
    combination_key = models.CharField(max_length=500)

    def __str__(self):
        return self.sku or f"{self.product} #{self.pk}"
