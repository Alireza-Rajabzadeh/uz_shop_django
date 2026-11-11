from django.db import models


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
        #: Dedicated UI calls them directly; never placed in a slot.
        SPECIAL = "special", "Special"

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
