from rest_framework import serializers

from ..services.landing_page_content_resolver import LandingPageContentResolver
from .page_serializer import PageSerializer


class PageDetailSerializer(PageSerializer):
    resolved_draft_content = serializers.SerializerMethodField()

    class Meta(PageSerializer.Meta):
        fields = [*PageSerializer.Meta.fields, "resolved_draft_content"]

    def get_resolved_draft_content(self, page):
        return LandingPageContentResolver.for_authoring().resolve(page.draft_content)
