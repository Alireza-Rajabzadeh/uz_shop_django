
from django.db import models


class CategoryDetailRelation(models.Model):
    category = models.ForeignKey("Category", on_delete=models.CASCADE)
    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("category", "detail")