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


class SuggestionPage(models.Model):
    """A page the panel offers to create on the vendor's behalf.

    This is shared reference data, not business-owned content: every vendor
    sees the same suggestions, so it deliberately has no `business` FK (that
    rule applies to `Page`/`LandingPage`, which a vendor actually authors).
    The *result* of acting on a suggestion is still a per-business `Page` —
    the suggestion only describes what to offer.

    `context` is the placement a suggestion's pages are authored in. The
    panel offers a component only when `context` appears in that component's
    `allowedContexts` contract field, so classifying a new component is one
    edit to its contract rather than a change to every suggestion row. It
    replaces the earlier `component_lists` allow-list, which scaled with
    components x suggestions and could drift out of date on rename.
    """

    class Context(models.TextChoices):
        #: A full page: the ordinary case for every standard shop page.
        PAGE = "page", "Page"
        #: A block embedded inside a larger page.
        SECTION = "section", "Section"
        #: The site footer.
        FOOTER = "footer", "Footer"

    title = models.CharField(max_length=255)
    descriptions = models.TextField(blank=True, default="")
    required = models.BooleanField(default=False)
    activate = models.BooleanField(default=True)
    slug = models.SlugField(allow_unicode=True)
    context = models.CharField(
        max_length=16, choices=Context.choices, default=Context.PAGE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_content_suggestion_page"
        ordering = ["id"]
        constraints = [
            # Suggestions are identified by their canonical slug, so the
            # panel can match one against an existing page by slug alone.
            models.UniqueConstraint(
                fields=["slug"],
                name="business_content_suggestion_page_slug_unique",
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
        db_table = "business_content_seo_record"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "resource_id"],
                name="business_content_seo_resource_unique",
            )
        ]

    def __str__(self):
        return f"{self.resource_type}:{self.resource_id}"
