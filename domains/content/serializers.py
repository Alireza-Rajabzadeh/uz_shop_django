from rest_framework import serializers

from .contracts import empty_draft_content, validate_draft_content
from .models import LandingPage


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
