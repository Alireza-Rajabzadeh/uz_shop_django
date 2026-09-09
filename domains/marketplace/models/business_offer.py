from django.db import models

from core.constants import DISCOUNT_TYPES


class BusinessOffer(models.Model):
    class Meta:
        db_table = "marketplace_business_offer"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "variant"],
                name="marketplace_offer_business_variant_unique",
            ),
        ]

    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.PROTECT,
        related_name="offers",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="business_offers",
    )
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0)
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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.business} → {self.variant}"
