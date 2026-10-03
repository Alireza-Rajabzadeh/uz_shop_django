from django.core.validators import validate_unicode_slug
from django.utils.translation import gettext as _
from rest_framework import serializers

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage, Page, SEORecord
from .services import LandingPageContentResolver, SEOService


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


class LandingPageSerializer(BusinessSlugScopeMixin, serializers.ModelSerializer):
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


class PageSerializer(BusinessSlugScopeMixin, serializers.ModelSerializer):
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
