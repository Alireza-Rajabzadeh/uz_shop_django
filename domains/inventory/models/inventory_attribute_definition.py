from django.core.exceptions import ValidationError
from django.db import models

from ..enums.InventoryAttributeTypeEnum import InventoryAttributeTypeEnum


class InventoryAttributeDefinition(models.Model):
    class Meta:
        db_table = "inventory_attribute_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"],
                name="inventory_attrdef_business_code_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["business"], name="invattrdef_business_idx"),
        ]
        ordering = ["business", "name"]

    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="inventory_attribute_definitions",
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)
    type = models.CharField(
        max_length=20,
        choices=InventoryAttributeTypeEnum.choices(),
        default=InventoryAttributeTypeEnum.TEXT.value,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        import re
        self.code = re.sub(r"[^a-z0-9]+", "_", self.code.strip().lower()).strip("_")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.type})"
