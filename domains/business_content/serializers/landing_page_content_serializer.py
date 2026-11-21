from rest_framework import serializers

from ..models import LandingPage
from ..services.seo_service import SEOService


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
