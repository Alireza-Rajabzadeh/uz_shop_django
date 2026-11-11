from django.db import models


class LandingPage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    slug = models.SlugField(allow_unicode=True)
    draft_content = models.JSONField(default=dict, blank=True)
    published_content = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField(null=True, blank=True)
    cache_ttl = models.PositiveIntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_landing_page"
        ordering = ["-updated_at"]
        constraints = [
            # Platform-owned content only: every row belongs to the shared
            # storefront, so slugs are globally unique. Business-owned pages
            # live in `domains.business_content`.
            models.UniqueConstraint(
                fields=["slug"],
                name="content_landing_page_slug_unique",
            ),
        ]

    def __str__(self):
        return self.title
