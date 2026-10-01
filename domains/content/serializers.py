from django.core.validators import validate_unicode_slug
from rest_framework import serializers

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage, Page, SEORecord
from .services import LandingPageContentResolver, SEOService


class ContentSlugScopeMixin:
    """Slug uniqueness is scoped, not global.

    The view passes the requesting business through the serializer context.
    Admin edits without context inherit the row's own owner, and a create
    without context targets the shared scope (`business IS NULL`). The DB
    constraints in the models back this up, but a serializer check keeps
    duplicates a 400 instead of an IntegrityError.

    The serializers declare ``slug`` and ``Meta.validators = []`` explicitly
    so DRF does not build its own uniqueness validators from those
    constraints: they would validate the wrong scope (or none at all),
    because the authoring business lives in the view, not in the payload.
    """

    def validate_slug(self, slug):
        business = self.context.get("business")
        if business is None and self.instance is not None:
            # No scope in context means an admin edit: inherit the row's owner
            # so a rename stays unique inside the scope the row lives in.
            business = self.instance.business
        matches = self.Meta.model.objects.filter(slug=slug, business=business)
        if self.instance is not None:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError(
                "A content item with this slug already exists in this scope."
            )
        return slug


class LandingPageSerializer(ContentSlugScopeMixin, serializers.ModelSerializer):
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


class PageSerializer(ContentSlugScopeMixin, serializers.ModelSerializer):
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
