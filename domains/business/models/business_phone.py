from django.db import models

from .base import ImmutableKeyModel
from .choices import RecordStatus, Visibility


class BusinessPhone(ImmutableKeyModel):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="phones",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=120)
    number = models.CharField(max_length=40)
    extension = models.CharField(max_length=16, blank=True)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACTIVE)
    notes = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "business_phone"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "key"], name="business_phone_business_key_unique"),
        ]

    def __str__(self):
        return self.title
