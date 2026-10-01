from django.db import models


class LandingPage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    #: NULL marks shared storefront content owned by the admin. A business
    #: owns its own rows, and vendors only ever see theirs.
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="landing_pages",
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
        db_table = "content_landing_page"
        ordering = ["-updated_at"]
        constraints = [
            # Slugs only have to be unique inside one scope: per business, or
            # across the shared (business IS NULL) rows. Postgres treats NULLs
            # as distinct, so the shared scope needs its own partial unique.
            models.UniqueConstraint(
                fields=["business", "slug"],
                name="content_landing_page_business_slug_unique",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(business__isnull=True),
                name="content_landing_page_global_slug_unique",
            ),
        ]

    def __str__(self):
        return self.title


class Page(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    #: NULL marks shared storefront content owned by the admin (including the
    #: `home` page). Business rows never serve on the public slug routes.
    business = models.ForeignKey(
        "business.BusinessProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="content_pages",
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
        db_table = "content_page"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "slug"],
                name="content_page_business_slug_unique",
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(business__isnull=True),
                name="content_page_global_slug_unique",
            ),
        ]

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
