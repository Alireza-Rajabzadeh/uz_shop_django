from django.core.validators import validate_unicode_slug
from rest_framework import serializers

from ..contracts import empty_draft_content, validate_draft_content
from ..models import LandingPage
from .business_slug_scope_mixin import BusinessSlugScopeMixin
from .content_context_scope_mixin import ContentContextScopeMixin


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
