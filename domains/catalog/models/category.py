
from django.db import models

class CategoryStatus(models.Model):
    class Meta:
        db_table = "catalog_category_status"
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
    
class Category(models.Model):
    
    class Meta:
        db_table = "catalog_category"
    
    name = models.CharField(max_length=100)

    status = models.ForeignKey(
        "CategoryStatus",
        on_delete=models.PROTECT,
        related_name="categories",
        default=1
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children"
    )
    logo=models.CharField(
        max_length=250,
        null=True,
        blank=True
        );
    

    def __str__(self):
        return self.name