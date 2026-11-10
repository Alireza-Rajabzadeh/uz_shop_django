from django.db import models

from .base import ImmutableKeyModel
from .choices import RecordStatus, Visibility
from .social_media import SocialMedia
from .social_media_icon import SocialMediaIcon


class BusinessSocialLink(ImmutableKeyModel):
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="social_links",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=120)
    social_media = models.ForeignKey(
        SocialMedia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_links",
    )
    url = models.URLField(max_length=500)
    icon = models.ForeignKey(
        SocialMediaIcon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_links",
    )
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACTIVE)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "business_social_link"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "key"], name="business_social_link_business_key_unique"),
        ]

    def __str__(self):
        return self.title
