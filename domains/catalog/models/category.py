
from django.db import models
from django.db.models.functions import Lower, Trim

class CategoryStatus(models.Model):
    class Meta:
        db_table = "catalog_category_status"
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
    
class Category(models.Model):
    
    class Meta:
        db_table = "catalog_category"
        permissions = [
            ("assign_details_to_category", "Can assign details to category"),
            (
                "assign_variant_attributes_to_category",
                "Can assign variant attributes to category",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_category_normalized_name_unique",
            ),
        ]
    
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
