from django.db import models


class LandingPage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    #: Every row belongs to a business. There is deliberately no shared/admin
    #: scope here: platform-owned content lives in `domains.content`.
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="business_content_landing_pages",
    )
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
        db_table = "business_content_landing_page"
        ordering = ["-updated_at"]
        constraints = [
            # `business` is required, so one scope constraint is enough: slugs
            # only have to be unique inside the owning business.
            models.UniqueConstraint(
                fields=["business", "slug"],
                name="business_content_landing_page_business_slug_unique",
            ),
        ]

    def __str__(self):
        return self.title
