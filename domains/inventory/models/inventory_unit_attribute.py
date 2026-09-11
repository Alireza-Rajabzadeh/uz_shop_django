from django.core.exceptions import ValidationError
from django.db import models


class InventoryUnitAttribute(models.Model):
    class Meta:
        db_table = "inventory_unit_attribute"
        constraints = [
            models.UniqueConstraint(
                fields=["inventory_unit", "attribute_definition"],
                name="invunitattr_unit_def_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["inventory_unit"], name="invunitattr_unit_idx"),
            models.Index(fields=["attribute_definition"], name="invunitattr_def_idx"),
        ]

    inventory_unit = models.ForeignKey(
        "InventoryUnit",
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    attribute_definition = models.ForeignKey(
        "InventoryAttributeDefinition",
        on_delete=models.CASCADE,
        related_name="unit_attributes",
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
