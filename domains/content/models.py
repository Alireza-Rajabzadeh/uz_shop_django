from django.db import models


class LandingPage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, allow_unicode=True)
    draft_content = models.JSONField(default=dict, blank=True)
    published_content = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_landing_page"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class SEORecord(models.Model):
    resource_type = models.CharField(max_length=64)
    resource_id = models.BigIntegerField()
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    canonical_url = models.URLField(null=True, blank=True)
    image_id = models.BigIntegerField(null=True, blank=True)
    index = models.BooleanField(default=True)
    follow = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_seo_record"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "resource_id"],
                name="content_seo_resource_unique",
            )
        ]

    def __str__(self):
        return f"{self.resource_type}:{self.resource_id}"
