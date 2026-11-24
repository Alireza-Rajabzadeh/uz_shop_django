from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
import domains.business_content.views as bc_views
from ..cache import landing_page_cache_key
from ..models import LandingPage
from ..serializers.landing_page_content_serializer import (
    LandingPageContentSerializer,
)
from ..services.landing_page_content_resolver import LandingPageContentResolver
from ..services.landing_page_service import LandingPageService
from ..services.public import public_business_id


class LandingPageBySlug(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = ()
    content_field = ""
    resolver_factory = LandingPageContentResolver

    def get(self, request, slug):
        try:
            page = LandingPageService().get_by_slug(slug)
        except LandingPage.DoesNotExist as exc:
            raise NotFound(_("Landing page not found.")) from exc

        if page.status not in self.allowed_statuses:
            raise NotFound(_("Landing page not found."))

        page.selected_content = self.resolver_factory().resolve(
            getattr(page, self.content_field)
        )
        return api_response(data=LandingPageContentSerializer(page).data)


class PublicLandingPage(LandingPageBySlug):
    allowed_statuses = (LandingPage.Status.PUBLISHED,)
    content_field = "published_content"

    def resolve_payload(self, request, slug):
        response = super().get(request, slug)
        page = LandingPage.objects.only("cache_ttl").get(
            slug=slug, business_id=public_business_id()
        )
        return response.data["data"], page.cache_ttl

    def get(self, request, slug):
        key = landing_page_cache_key(slug)
        cache = getattr(bc_views, "CacheService", CacheService)()
        cached = cache.get_public(key)
        if cached is not None:
            return api_response(data=cached)
        data = cache.get_or_set_public(
            key, lambda: self.resolve_payload(request, slug)
        )
        return api_response(data=data)
