
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.text import slugify

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
        indexes = [
            models.Index(
                fields=["status", "id"],
                name="catalog_product_status_idx",
            ),
            GinIndex(
                fields=["name"],
                name="catalog_product_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["description"],
                name="catalog_product_desc_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ]
        
   
    name = models.CharField(max_length=250)
    slug = models.SlugField(max_length=280, unique=True, editable=False)
    status = models.ForeignKey(
        "ProductStatus",
        on_delete=models.PROTECT,
        related_name="status_products"
    )

    categories = models.ManyToManyField(
        "Category",
        related_name="products",
        blank=True,
        db_table="catalog_product_categories",
    )

    brand = models.ForeignKey(
        "Brand",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    
    description = models.TextField(blank=True,null=True)
    json_description = models.JSONField(default=dict, blank=True)
    

    
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)[:250] or "product"
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:270 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)
