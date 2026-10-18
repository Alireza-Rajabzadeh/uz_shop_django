from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .base import TimestampedModel


class VendorClubActivity(TimestampedModel):
    """A point-earning action a vendor can complete.

    `code` is the stable identifier callers key off, so it is created once and
    never edited; `name` and `description` are editable display text. An
    activity is retired by clearing `is_active`, never by deleting it, because
    ledger rows point at the activity for the life of the program.
    """

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    points = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "vendors_club_activity"
        ordering = ["id"]
        verbose_name_plural = "vendor club activities"
        constraints = [
            models.CheckConstraint(
                condition=Q(points__gt=0),
                name="vendors_club_activity_points_gt_zero",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored is not None and stored != self.code:
                raise ValidationError(
                    {"code": _("Code cannot be changed after creation.")}
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code
