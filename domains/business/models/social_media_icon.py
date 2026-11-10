from django.db import models

from .base import TimestampedModel
from .social_media import SocialMedia


class SocialMediaIcon(TimestampedModel):
    social_media = models.ForeignKey(
        SocialMedia,
        on_delete=models.CASCADE,
        related_name="icons",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.CASCADE,
        related_name="social_media_icons",
    )
    label = models.CharField(max_length=80, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "social_media_icon"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.social_media.name} - {self.label or self.file.original_name}"
