from rest_framework import serializers

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage, Page, SEORecord
from .services import LandingPageContentResolver


class LandingPageSerializer(serializers.ModelSerializer):
    draft_content = serializers.JSONField(
        required=False,
        default=empty_draft_content,
        validators=[validate_draft_content],
    )

    class Meta:
        model = LandingPage
        fields = [
            "id",
            "title",
            "slug",
            "draft_content",
            "published_content",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LandingPageContentSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()

    class Meta:
        model = LandingPage
        fields = ["id", "title", "slug", "status", "content"]

    @staticmethod
    def _normalize_content(content):
        if not isinstance(content, dict):
            content = {}
        if not isinstance(content.get("components"), list):
            content = {**content, "components": []}
        return content

    def get_content(self, page):
        return self._normalize_content(getattr(page, "selected_content", None))


class LandingPageDetailSerializer(LandingPageSerializer):
    resolved_draft_content = serializers.SerializerMethodField()

    class Meta(LandingPageSerializer.Meta):
        fields = [*LandingPageSerializer.Meta.fields, "resolved_draft_content"]

    def get_resolved_draft_content(self, page):
        return LandingPageContentResolver.for_authoring().resolve(page.draft_content)


class PageSerializer(serializers.ModelSerializer):
    draft_content = serializers.JSONField(
        required=False,
        default=empty_draft_content,
        validators=[validate_draft_content],
    )

    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "draft_content",
            "published_content",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PageContentSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ["id", "title", "slug", "status", "content"]

    def get_content(self, page):
        return LandingPageContentSerializer._normalize_content(
            getattr(page, "selected_content", None)
        )


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
