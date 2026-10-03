from django.core.validators import validate_unicode_slug
from django.utils.translation import gettext as _
from rest_framework import serializers

from .contracts import empty_draft_content, enforce_draft_context, validate_draft_content
from .models import LandingPage, Page, SEORecord, SuggestionPage
from .services import LandingPageContentResolver, SEOService


class ContentContextScopeMixin:
    """Restrict ``draft_content`` to the components allowed for this row's context.

    A page's context is whatever the `SuggestionPage` holding its canonical
    slug declares, so the panel's suggestion list and the API agree on what a
    page is without a foreign key — changing a suggestion's context applies
    immediately to every page carrying that slug. A slug outside the standard
    set falls back to the default context, which every component currently
    allows, so an arbitrary page is never locked out of its own vocabulary.

    The slug is read from the payload on create and from the stored row on
    update, so a PATCH that omits ``slug`` still resolves against the saved one.
    """

    def validate_draft_content(self, value):
        slug = getattr(self, "initial_data", {}).get("slug")
        if not isinstance(slug, str) or not slug.strip():
            slug = getattr(self.instance, "slug", "")
        # `iexact` because the panels normalize the slug they match on (trim +
        # lowercase) before resolving a context, and the two must agree.
        context = (
            SuggestionPage.objects.filter(slug__iexact=str(slug).strip())
            .values_list("context", flat=True)
            .first()
            or SuggestionPage.Context.PAGE.value
        )
        return enforce_draft_context(value, context)


class BusinessSlugScopeMixin:
    """Slug uniqueness is scoped to the owning business.

    The view always puts the caller's business in the serializer context, and
    ``business`` is never accepted from the payload — it is assigned on
    ``save()``. The DB constraint in the models backs this up, but a serializer
    check keeps duplicates a 400 instead of an IntegrityError.

    The serializers declare ``slug`` and ``Meta.validators = []`` explicitly so
    DRF does not build its own uniqueness validators from that constraint:
    they would validate across every business, because the authoring business
    lives in the view, not in the payload.
    """

    def validate_slug(self, slug):
        business = self.context.get("business")
        if business is None:
            return slug
        matches = self.Meta.model.objects.filter(slug=slug, business=business)
        if self.instance is not None:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError(
                _("A content item with this slug already exists in this scope.")
            )
        return slug


class LandingPageSerializer(
    BusinessSlugScopeMixin, ContentContextScopeMixin, serializers.ModelSerializer
):
    slug = serializers.SlugField(
        max_length=50,
        allow_unicode=True,
        validators=[validate_unicode_slug],
    )
    draft_content = serializers.JSONField(
        required=False,
        default=empty_draft_content,
        validators=[validate_draft_content],
    )

    class Meta:
        model = LandingPage
        validators = []
        fields = [
            "id",
            "business",
            "title",
            "slug",
            "draft_content",
            "published_content",
            "status",
            "published_at",
            "cache_ttl",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "created_at", "updated_at"]


class LandingPageContentSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        model = LandingPage
        fields = ["id", "title", "slug", "status", "content", "seo"]

    @staticmethod
    def _normalize_content(content):
        if not isinstance(content, dict):
            content = {}
        if not isinstance(content.get("components"), list):
            content = {**content, "components": []}
        return content

    def get_content(self, page):
        return self._normalize_content(getattr(page, "selected_content", None))

    def get_seo(self, page):
        return SEOService.get_for("landing_page", page.id)


class LandingPageDetailSerializer(LandingPageSerializer):
    resolved_draft_content = serializers.SerializerMethodField()

    class Meta(LandingPageSerializer.Meta):
        fields = [*LandingPageSerializer.Meta.fields, "resolved_draft_content"]

    def get_resolved_draft_content(self, page):
        return LandingPageContentResolver.for_authoring().resolve(page.draft_content)


class PageSerializer(
    BusinessSlugScopeMixin, ContentContextScopeMixin, serializers.ModelSerializer
):
    slug = serializers.SlugField(
        max_length=50,
        allow_unicode=True,
        validators=[validate_unicode_slug],
    )
    draft_content = serializers.JSONField(
        required=False,
        default=empty_draft_content,
        validators=[validate_draft_content],
    )

    class Meta:
        model = Page
        validators = []
        fields = [
            "id",
            "business",
            "title",
            "slug",
            "draft_content",
            "published_content",
            "status",
            "published_at",
            "cache_ttl",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "business", "created_at", "updated_at"]


class PageContentSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ["id", "title", "slug", "status", "content", "seo"]

    def get_content(self, page):
        return LandingPageContentSerializer._normalize_content(
            getattr(page, "selected_content", None)
        )

    def get_seo(self, page):
        return SEOService.get_for("page", page.id)


class PageDetailSerializer(PageSerializer):
    resolved_draft_content = serializers.SerializerMethodField()

    class Meta(PageSerializer.Meta):
        fields = [*PageSerializer.Meta.fields, "resolved_draft_content"]

    def get_resolved_draft_content(self, page):
        return LandingPageContentResolver.for_authoring().resolve(page.draft_content)


class SEORecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SEORecord
        fields = [
            "id",
            "resource_type",
            "resource_id",
            "title",
            "description",
            "canonical_url",
            "image_id",
            "index",
            "follow",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "resource_type", "resource_id", "created_at", "updated_at"]


class SuggestionPageSerializer(serializers.ModelSerializer):
    """Read-only projection of the pages the panel offers to create.

    ``activate`` is a management flag the view filters on server-side, so it
    is not sent to the panels. ``context`` is: the editor filters the component
    palette by it, matching the ``allowedContexts`` each contract declares.
    """

    class Meta:
        model = SuggestionPage
        fields = ["id", "title", "descriptions", "required", "slug", "context"]
        read_only_fields = fields
