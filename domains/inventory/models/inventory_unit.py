from django.core.exceptions import ValidationError
from django.db import models

from ..enums.InventoryUnitStateEnum import InventoryUnitStateEnum


class InventoryUnit(models.Model):
    class Meta:
        db_table = "inventory_unit"
        indexes = [
            models.Index(fields=["inventory", "state"], name="invunit_inventory_state_idx"),
            models.Index(fields=["state"], name="invunit_state_idx"),
            models.Index(fields=["supply"], name="invunit_supply_idx"),
            models.Index(fields=["created_at"], name="invunit_created_idx"),
        ]

    inventory = models.ForeignKey(
        "Inventory",
        on_delete=models.PROTECT,
        related_name="units",
    )
    state = models.CharField(
        max_length=20,
        choices=InventoryUnitStateEnum.choices(),
        default=InventoryUnitStateEnum.IN_STOCK.value,
    )
    supply = models.ForeignKey(
        "InventorySupply",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="units",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        errors = {}
        if self.supply and self.supply.variant_id != self.inventory.variant_id:
            errors["supply"] = (
                "Supply must match the inventory's variant."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Unit #{self.pk} ({self.get_state_display()}) @ {self.inventory}"
