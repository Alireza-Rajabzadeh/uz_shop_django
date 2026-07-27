from django.db import models
from django.db.models.functions import Lower, Trim

from core.constants import CATEGORY_DETAIL_TYPE_CHOICES


class CategoryDetail(models.Model):
    class Meta:
        db_table = "catalog_category_detail"
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_category_detail_normalized_name_unique",
            ),
        ]

    name = models.CharField(max_length=100)

    type = models.CharField(max_length=20, choices=CATEGORY_DETAIL_TYPE_CHOICES)

    required = models.BooleanField(default=False)

    options = models.CharField(max_length=100, blank=True, default="")

    filterable = models.BooleanField(default=True)

    def __str__(self):
        return self.name
