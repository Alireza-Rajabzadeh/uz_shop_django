
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils.text import slugify

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
                condition=models.Q(parent__isnull=True),
                name="catalog_root_category_normalized_name_unique",
            ),
            models.UniqueConstraint(
                models.F("parent"),
                Lower(Trim("name")),
                condition=models.Q(parent__isnull=False),
                name="catalog_child_category_normalized_name_unique",
            ),
        ]
    
    name = models.CharField(max_length=100)
    fa_name = models.CharField(max_length=100, blank=True, null=True)
    slug = models.SlugField(max_length=100, unique=True, editable=False)

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

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)[:80] or "category"
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:90 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)
