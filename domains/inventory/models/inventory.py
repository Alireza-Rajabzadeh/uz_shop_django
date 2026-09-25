from django.core.exceptions import ValidationError
from django.db import models


class Inventory(models.Model):
    class Meta:
        db_table = "inventory_inventory"
        permissions = [
            ("adjust_stock", "Can adjust stock"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "variant"],
                name="inventory_warehouse_variant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="inventory_quantity_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(sellable__gte=0),
                name="inventory_sellable_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved__gte=0),
                name="inventory_reserved_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(sellable__lte=models.F("quantity")),
                name="inventory_sellable_lte_quantity",
            ),
        ]
        indexes = [
            models.Index(fields=["variant", "warehouse"], name="inv_variant_wh_idx"),
            models.Index(fields=["business"], name="inv_business_idx"),
            models.Index(fields=["warehouse"], name="inv_warehouse_idx"),
        ]

    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.PROTECT,
        related_name="inventories",
    )
    warehouse = models.ForeignKey(
        "Warehouse",
        on_delete=models.PROTECT,
        related_name="inventories",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariants",
        on_delete=models.PROTECT,
        related_name="inventories",
    )
    inventory_type = models.ForeignKey(
        "InventoryType",
        on_delete=models.PROTECT,
        related_name="inventories",
        default=1,
    )
    quantity = models.PositiveIntegerField(default=0)
    sellable = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def available(self):
        return self.sellable - self.reserved

    def clean(self):
        errors = {}
        if self.warehouse_id and self.business_id:
            if self.warehouse.business_id and self.warehouse.business_id != self.business_id:
                errors["business"] = (
                    "Business must match the warehouse's business."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.variant.sku} @ {self.warehouse.code}: {self.available}"
