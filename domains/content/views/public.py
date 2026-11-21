from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
import domains.content.views as content_views
from ..cache import HOME_CACHE_KEY, landing_page_cache_key, page_cache_key
from ..models.landing_page import LandingPage
from ..models.page import Page
from ..serializers.landing_page_content_serializer import (
    LandingPageContentSerializer,
)
from ..serializers.page_content_serializer import PageContentSerializer
from ..services.landing_page_content_resolver import LandingPageContentResolver
from ..services.landing_page_service import LandingPageService
from ..services.page_service import PageService
from ..services.seo_service import SEOService


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
        page = LandingPage.objects.only("cache_ttl").get(slug=slug)
        return response.data["data"], page.cache_ttl

    def get(self, request, slug):
        key = landing_page_cache_key(slug)
        cache = getattr(content_views, "CacheService", CacheService)()
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

    def resolve_payload(self):
        try:
            page = PageService().get_home_page()
        except Page.DoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if page.status != Page.Status.PUBLISHED:
            raise NotFound(_("Page not found."))

        resolver_cls = getattr(
            content_views, "LandingPageContentResolver", LandingPageContentResolver
        )
        page.selected_content = resolver_cls().resolve(
            page.published_content
        )
        return PageContentSerializer(page).data, page.cache_ttl

    def get(self, request):
        cache = getattr(content_views, "CacheService", CacheService)()
        cached = cache.get_public(HOME_CACHE_KEY)
        if cached is not None:
            return api_response(data=cached)
        data = cache.get_or_set_public(HOME_CACHE_KEY, self.resolve_payload)
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
        page = Page.objects.only("cache_ttl").get(slug=slug)
        return response.data["data"], page.cache_ttl

    def get(self, request, slug):
        key = page_cache_key(slug)
        cache = getattr(content_views, "CacheService", CacheService)()
        cached = cache.get_public(key)
        if cached is not None:
            return api_response(data=cached)
        data = cache.get_or_set_public(
            key, lambda: self.resolve_payload(request, slug)
        )
        return api_response(data=data)


class PublicResourceSEO(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, resource_type, slug):
        payload = SEOService.get_public_resource(resource_type, slug)
        if payload is None:
            raise NotFound(_("SEO resource not found."))
        return api_response(data=payload)
