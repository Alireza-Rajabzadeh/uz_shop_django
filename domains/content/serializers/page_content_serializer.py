from rest_framework import serializers

from ..models.page import Page
from ..services.seo_service import SEOService
from .landing_page_content_serializer import LandingPageContentSerializer


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
