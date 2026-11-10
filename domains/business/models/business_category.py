from django.db import models

from .base import TimestampedModel
from .business_profile import BusinessProfile


class BusinessCategory(TimestampedModel):
    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.CASCADE,
        related_name="business_categories",
    )

    class Meta:
        db_table = "business_category"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "category"],
                name="business_category_unique",
            ),
        ]

    def __str__(self):
        return f"{self.business} → {self.category}"
