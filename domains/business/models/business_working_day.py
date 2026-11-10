from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .base import TimestampedModel


class BusinessWorkingDay(TimestampedModel):
    vendor = models.ForeignKey(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="business_working_days",
        null=True,
        blank=True,
    )
    weekday = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(6)])
    is_open = models.BooleanField(default=False)
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    second_opens_at = models.TimeField(null=True, blank=True)
    second_closes_at = models.TimeField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "business_working_day"
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["vendor", "weekday"], name="business_working_day_vendor_weekday_unique"),
            models.CheckConstraint(condition=Q(weekday__gte=0, weekday__lte=6), name="business_working_day_weekday_range"),
            models.CheckConstraint(condition=(Q(second_opens_at__isnull=True, second_closes_at__isnull=True) | Q(second_opens_at__isnull=False, second_closes_at__isnull=False)), name="business_working_day_second_pair"),
        ]

    def __str__(self):
        return str(self.weekday)
