from rest_framework import serializers

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage
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
    content = serializers.JSONField(source="selected_content", read_only=True)

    class Meta:
        model = LandingPage
        fields = ["id", "title", "slug", "status", "content"]


class LandingPageDetailSerializer(LandingPageSerializer):
    resolved_draft_content = serializers.SerializerMethodField()

    class Meta(LandingPageSerializer.Meta):
        fields = [*LandingPageSerializer.Meta.fields, "resolved_draft_content"]

    def get_resolved_draft_content(self, page):
        return LandingPageContentResolver.for_authoring().resolve(page.draft_content)
