from django.db import models

from core.constants import CATEGORY_DETAIL_TYPE_CHOICES


class CategoryDetail(models.Model):
    class Meta:
        db_table = "catalog_category_detail"

    name = models.CharField(max_length=100, unique=True)

    type = models.CharField(max_length=20, choices=CATEGORY_DETAIL_TYPE_CHOICES)

    required = models.BooleanField(default=False)

    options = models.CharField(max_length=100)

    filterable = models.BooleanField(default=True)

    def __str__(self):
        return self.name