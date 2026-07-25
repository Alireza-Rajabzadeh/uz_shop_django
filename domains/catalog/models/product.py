
from django.db import models
from core.constants import DISCOUNT_TYPES

class ProductStatus(models.Model):
    
    class Meta:
        db_table = "catalog_product_status"
    name = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return self.name
    
    
class Product(models.Model):
    class Meta:
        db_table = "catalog_product"
        permissions = [
            ("add_detail_to_product", "Can add product details"),
            ("add_variant_to_product", "Can add product variants"),
        ]
        
   
    name = models.CharField(max_length=250)
    status = models.ForeignKey(
        "ProductStatus",
        on_delete=models.PROTECT,
        related_name="status_products"
    )

    category = models.ForeignKey(
            "Category",
            on_delete=models.PROTECT,
            related_name="category_products"
      )
    
    description = models.TextField(blank=True,null=True)
    

    
    
    def __str__(self):
        return self.name