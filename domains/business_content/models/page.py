from django.db import models


class Page(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    #: Required owner. The platform `home` page is not duplicated here; a
    #: business home only exists once the business creates it.
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        related_name="business_content_pages",
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
        db_table = "business_content_page"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "slug"],
                name="business_content_page_business_slug_unique",
            ),
        ]

    def __str__(self):
        return self.title
