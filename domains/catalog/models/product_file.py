from django.db import models
from django.db.models import Q


class ProductFile(models.Model):
    class Role(models.TextChoices):
        GALLERY = "gallery", "Gallery"
        THUMBNAIL = "thumbnail", "Thumbnail"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name="product_files",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="product_files",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    alt_text = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_product_file"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "file"],
                name="catalog_product_file_unique",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_product_file_one_primary",
            ),
        ]
        indexes = [
            models.Index(
                fields=["product", "role", "position"],
                name="catalog_prod_file_order_idx",
            ),
        ]

    def __str__(self):
        return f"{self.product} - {self.file}"
