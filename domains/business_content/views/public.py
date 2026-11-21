from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
import domains.business_content.views as bc_views
from domains.business.models import BusinessProfile
from ..cache import (
    NEGATIVE_CACHE_TTL,
    home_cache_key,
    landing_page_cache_key,
    page_cache_key,
)
from ..models import LandingPage, Page
from ..serializers.landing_page_content_serializer import (
    LandingPageContentSerializer,
)
from ..serializers.page_content_serializer import PageContentSerializer
from ..services.landing_page_content_resolver import LandingPageContentResolver
from ..services.landing_page_service import LandingPageService
from ..services.page_service import PageService
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


class LandingPagePreview(LandingPageBySlug):
    allowed_statuses = (LandingPage.Status.DRAFT, LandingPage.Status.PUBLISHED)
    content_field = "draft_content"
    resolver_factory = LandingPageContentResolver.for_preview


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


class PublicHomePage(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _resolve_business(self, request):
        business = getattr(request, "business", None)
        if business is not None:
            return business
        business_id = getattr(request, "business_id", None)
        if business_id is not None:
            return BusinessProfile.objects.filter(id=business_id).first()
        if not request.headers.get("X-Tenant-Subdomain") and not request.META.get("HTTP_X_TENANT_SUBDOMAIN"):
            default_id = public_business_id()
            if default_id is not None:
                return BusinessProfile.objects.filter(id=default_id).first()
        return None

    def resolve_payload(self, business):
        service = PageService()
        if not service.allows_custom_homepage(business):
            return False, NEGATIVE_CACHE_TTL

        page = service.get_published_home_page(business)
        if page is None:
            return False, NEGATIVE_CACHE_TTL

        if not service.is_content_valid_for_rendering(page.published_content):
            return False, NEGATIVE_CACHE_TTL

        return service.resolve_home_page_data(page)

    def get(self, request):
        business = self._resolve_business(request)
        if business is None:
            raise NotFound(_("Page not found."))

        key = home_cache_key(business.id)
        cache = getattr(bc_views, "CacheService", CacheService)()

        cached = cache.get_public(key)
        if cached is not None:
            if cached is False:
                raise NotFound(_("Page not found."))
            return api_response(data=cached)

        data = cache.get_or_set_public(key, lambda: self.resolve_payload(business))
        if data is False:
            raise NotFound(_("Page not found."))

        return api_response(data=data)


class PageBySlug(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = ()
    content_field = ""
    resolver_factory = LandingPageContentResolver

    def get(self, request, slug):
        try:
            page = PageService().get_by_slug(slug)
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if page.status not in self.allowed_statuses:
            raise NotFound(_("Page not found."))

        page.selected_content = self.resolver_factory().resolve(
            getattr(page, self.content_field)
        )
        return api_response(data=PageContentSerializer(page).data)


class PagePreview(PageBySlug):
    allowed_statuses = (Page.Status.DRAFT, Page.Status.PUBLISHED)
    content_field = "draft_content"
    resolver_factory = LandingPageContentResolver.for_preview


class PublicPage(PageBySlug):
    allowed_statuses = (Page.Status.PUBLISHED,)
    content_field = "published_content"

    def resolve_payload(self, request, slug):
        response = super().get(request, slug)
        page = Page.objects.only("cache_ttl").get(
            slug=slug, business_id=public_business_id()
        )
        return response.data["data"], page.cache_ttl

    def get(self, request, slug):
        key = page_cache_key(slug)
        cache = getattr(bc_views, "CacheService", CacheService)()
        cached = cache.get_public(key)
        if cached is not None:
            return api_response(data=cached)
        data = cache.get_or_set_public(
            key, lambda: self.resolve_payload(request, slug)
        )
        return api_response(data=data)
