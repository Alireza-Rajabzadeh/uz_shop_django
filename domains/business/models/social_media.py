from django.db import models

from .base import TimestampedModel


class SocialMedia(TimestampedModel):
    name = models.CharField(max_length=80)
    fa_name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "social_media"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name
