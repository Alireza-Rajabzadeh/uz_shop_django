
from django.db import models


class CategoryDetailRelation(models.Model):
    
    category = models.ForeignKey("Category", on_delete=models.CASCADE)
    detail = models.ForeignKey("CategoryDetail", on_delete=models.CASCADE)
    value = models.CharField(max_length=512)

    class Meta:
        db_table = "catalog_category_detail_relation"
        unique_together = ("category", "detail")