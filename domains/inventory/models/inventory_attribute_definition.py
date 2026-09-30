import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F

from ..enums.InventoryAttributeTypeEnum import InventoryAttributeTypeEnum


class InventoryAttributeDefinition(models.Model):
    """Unit attribute vocabulary in two scopes.

    ``business IS NULL`` marks a global definition shared by every business
    (seeded reference data such as ``serial_number`` or ``imei``). A row with a
    ``business`` is an attribute that business created because it could not
    find an existing one; the vendor API only ever exposes global rows plus
    the caller's own rows.

    ``code`` is the lookup and API contract. It is unique per business and,
    for global rows, unique across the table. ``code`` may still collide
    between a global row and a business row only if the business row existed
    before the global one was seeded, so
    ``InventoryAttributeService.resolve_definition`` always prefers the
    caller's own row and then the global row instead of relying on an
    arbitrary ``filter(code=...).first()``.
    """

    class Meta:
        db_table = "inventory_attribute_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"],
                name="inventory_attrdef_business_code_unique",
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=models.Q(business__isnull=True),
                name="inventory_attrdef_global_code_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["business"], name="invattrdef_business_idx"),
        ]
        # Global rows are shared reference data, so they sort first.
        ordering = [F("business").asc(nulls_first=True), "name"]

    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="inventory_attribute_definitions",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    fa_title = models.CharField(max_length=100, blank=True, default="")
    code = models.CharField(max_length=50)
    type = models.CharField(
        max_length=20,
        choices=InventoryAttributeTypeEnum.choices(),
        default=InventoryAttributeTypeEnum.TEXT.value,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_global(self):
        return self.business_id is None

    @property
    def display_title(self):
        """Persian title when present, English name as the fallback."""
        return self.fa_title or self.name

    def save(self, *args, **kwargs):
        self.code = re.sub(r"[^a-z0-9]+", "_", self.code.strip().lower()).strip("_")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_title} ({self.type})"
