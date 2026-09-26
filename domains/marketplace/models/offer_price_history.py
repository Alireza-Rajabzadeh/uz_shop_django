from django.db import models

from core.constants import DISCOUNT_TYPES
from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum

# Who triggered the recorded price/discount change.
SOURCE_ADMIN = "admin"
SOURCE_VENDOR = "vendor"


class OfferPriceHistory(models.Model):
    # Append-only audit of BusinessOffer price/discount changes. Written by the
    # marketplace service so both the admin offer API and the vendor variant API
    # leave the same trail. Inventory keeps its own VariantPriceHistory for the
    # cost-basis pricing flow; that record is intentionally separate.

    class Meta:
        db_table = "marketplace_offer_price_history"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["variant", "created_at"], name="oph_variant_created_idx"),
            models.Index(fields=["business", "created_at"], name="oph_business_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(old_price__gte=0),
                name="marketplace_offer_history_old_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(new_price__gte=0),
                name="marketplace_offer_history_new_price_gte_zero",
            ),
        ]

    offer = models.ForeignKey(
        "BusinessOffer",
        on_delete=models.PROTECT,
        related_name="price_history",
    )
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.PROTECT,
        related_name="offer_price_history",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="offer_price_history",
    )
    old_price = models.DecimalField(max_digits=15, decimal_places=2)
    new_price = models.DecimalField(max_digits=15, decimal_places=2)
    old_discount_type = models.CharField(
        max_length=20, choices=DISCOUNT_TYPES, blank=True, null=True
    )
    new_discount_type = models.CharField(
        max_length=20, choices=DISCOUNT_TYPES, blank=True, null=True
    )
    old_discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    new_discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    cost_strategy = models.CharField(
        max_length=20,
        choices=VariantCostStrategyEnum.choices(),
        default="latest",
    )
    expected_profit_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    source = models.CharField(
        max_length=20,
        choices=[(SOURCE_ADMIN, "Admin"), (SOURCE_VENDOR, "Vendor")],
        default=SOURCE_ADMIN,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def changed(self):
        return (
            self.old_price != self.new_price
            or self.old_discount_type != self.new_discount_type
            or self.old_discount_value != self.new_discount_value
        )

    def __str__(self):
        return f"{self.variant.sku}: {self.old_price} -> {self.new_price}"
