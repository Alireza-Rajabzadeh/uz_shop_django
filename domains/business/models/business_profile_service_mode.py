from django.db import models

from .base import TimestampedModel
from .business_profile import BusinessProfile
from .business_service_mode import BusinessServiceMode


class BusinessProfileServiceMode(TimestampedModel):
    """A service mode one business profile has enabled.

    ``business_profile`` cascades like the profile's other owned rows, so
    deleting a profile retires its selections with it. ``service_mode``
    protects the shared vocabulary: a mode a profile already selected is
    retired by clearing its ``is_active``, never deleted. The unique
    constraint makes a mode configurable at most once per profile; disabling
    keeps the row so the id and its history stay stable.
    """

    business_profile = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name="service_modes",
    )
    service_mode = models.ForeignKey(
        BusinessServiceMode,
        on_delete=models.PROTECT,
        related_name="profile_configurations",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "business_profile_service_mode"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_profile", "service_mode"],
                name="business_profile_service_mode_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["business_profile", "is_active"],
                name="bp_service_mode_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.business_profile} → {self.service_mode.code}"
