
from django.db import models

class CategoryStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
    
class Category(models.Model):
    name = models.CharField(max_length=100)

    status = models.ForeignKey(
        "CategoryStatus",
        on_delete=models.PROTECT,
        related_name="categories"
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children"
    )

    def __str__(self):
        return self.name