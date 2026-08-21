from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils.text import slugify


class Brand(models.Model):
    class Meta:
        db_table = "catalog_brand"
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_brand_normalized_name_unique",
            ),
        ]
        indexes = [
            GinIndex(
                fields=["name"],
                name="catalog_brand_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    name = models.CharField(max_length=150)
    fa_name = models.CharField(max_length=150, blank=True, null=True)
    slug = models.SlugField(max_length=150, unique=True, editable=False)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)[:120] or "brand"
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:140 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)
