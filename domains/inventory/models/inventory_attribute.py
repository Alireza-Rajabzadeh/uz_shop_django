from django.core.exceptions import ValidationError
from django.db import models


class InventoryAttribute(models.Model):
    class Meta:
        db_table = "inventory_attribute"
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "attribute_definition"],
                name="inventory_attr_inventory_def_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["inventory"], name="invattr_inventory_idx"),
            models.Index(fields=["attribute_definition"], name="invattr_def_idx"),
        ]

    inventory = models.ForeignKey(
        "Inventory",
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    attribute_definition = models.ForeignKey(
        "InventoryAttributeDefinition",
        on_delete=models.CASCADE,
        related_name="inventory_attributes",
    )
    value = models.TextField(blank=True, default="")

    def clean(self):
        errors = {}
        if self.attribute_definition_id and self.value:
            from domains.inventory.services.inventory_attribute_service import (
                InventoryAttributeService,
            )
            attr_def = self.attribute_definition
            if not InventoryAttributeService.validate_value(self.value, attr_def.type):
                errors["value"] = (
                    f"Value '{self.value}' is not valid for type '{attr_def.type}'."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.attribute_definition.name} = {self.value}"
