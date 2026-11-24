from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
from domains.business_content.models import LandingPage as BusinessLandingPage, Page as BusinessPage
from domains.business_content.serializers.landing_page_content_serializer import (
    LandingPageContentSerializer as BusinessLandingPageSerializer,
)
from domains.business_content.serializers.page_content_serializer import (
    PageContentSerializer as BusinessPageSerializer,
)
from domains.business_content.services import (
    LandingPageContentResolver as BusinessLandingPageContentResolver,
    LandingPageService as BusinessLandingPageService,
    PageService as BusinessPageService,
)
from domains.content.models import LandingPage as ContentLandingPage, Page as ContentPage
from domains.content.serializers.landing_page_content_serializer import (
    LandingPageContentSerializer as ContentLandingPageSerializer,
)
from domains.content.serializers.page_content_serializer import (
    PageContentSerializer as ContentPageSerializer,
)
from domains.content.services import (
    LandingPageContentResolver as ContentLandingPageContentResolver,
    LandingPageService as ContentLandingPageService,
    PageService as ContentPageService,
)

from ..cache import page_cache_key


class StorefrontPageView(APIView):
    """Customer-facing storefront page API.

    Returns published page content for platform or business storefronts.
    Defaults to slug 'home'.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug="home"):
        business = getattr(request, "business", None)
        cache_key = page_cache_key(slug, business_id=business)

        cache = CacheService()
        cached = cache.get_public(cache_key)
        if cached is not None:
            if cached is False:
                raise NotFound(_("Page not found."))
            return api_response(True, "", cached)

        if business is not None:
            try:
                data, ttl = BusinessPageService().get_storefront_page(
                    slug=slug, business=business
                )
            except NotFound:
                if slug == "home":
                    # Negative cache for businesses without a custom homepage (300s TTL)
                    cache.put_public(cache_key, False, ttl=300)
                raise
        else:
            data, ttl = ContentPageService().get_storefront_page(slug=slug)

        if ttl is None or ttl > 0:
            cache.put_public(cache_key, data, ttl=ttl)

        return api_response(True, "", data)


class StorefrontPagePreviewView(APIView):
    """Storefront preview API for pages.

    Returns draft content for platform or business pages.
    Allowed statuses: DRAFT, PUBLISHED.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = (ContentPage.Status.DRAFT, ContentPage.Status.PUBLISHED)

    def get(self, request, slug):
        business = getattr(request, "business", None)
        if business is not None:
            try:
                page = BusinessPageService().get_by_slug(slug, business_id=business.id)
            except BusinessPage.DoesNotExist as exc:
                raise NotFound(_("Page not found.")) from exc

            if page.status not in self.allowed_statuses:
                raise NotFound(_("Page not found."))

            page.selected_content = BusinessLandingPageContentResolver.for_preview().resolve(
                page.draft_content
            )
            return api_response(True, "", BusinessPageSerializer(page).data)
        else:
            try:
                page = ContentPageService().get_by_slug(slug)
            except ContentPage.DoesNotExist as exc:
                raise NotFound(_("Page not found.")) from exc

            if page.status not in self.allowed_statuses:
                raise NotFound(_("Page not found."))

            page.selected_content = ContentLandingPageContentResolver.for_preview().resolve(
                page.draft_content
            )
            return api_response(True, "", ContentPageSerializer(page).data)


class StorefrontLandingPagePreviewView(APIView):
    """Storefront preview API for landing pages.

    Returns draft content for platform or business landing pages.
    Allowed statuses: DRAFT, PUBLISHED.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    allowed_statuses = (ContentLandingPage.Status.DRAFT, ContentLandingPage.Status.PUBLISHED)

    def get(self, request, slug):
        business = getattr(request, "business", None)
        if business is not None:
            try:
                page = BusinessLandingPageService().get_by_slug(slug, business_id=business.id)
            except BusinessLandingPage.DoesNotExist as exc:
                raise NotFound(_("Landing page not found.")) from exc

            if page.status not in self.allowed_statuses:
                raise NotFound(_("Landing page not found."))

            page.selected_content = BusinessLandingPageContentResolver.for_preview().resolve(
                page.draft_content
            )
            return api_response(True, "", BusinessLandingPageSerializer(page).data)
        else:
            try:
                page = ContentLandingPageService().get_by_slug(slug)
            except ContentLandingPage.DoesNotExist as exc:
                raise NotFound(_("Landing page not found.")) from exc

            if page.status not in self.allowed_statuses:
                raise NotFound(_("Landing page not found."))

            page.selected_content = ContentLandingPageContentResolver.for_preview().resolve(
                page.draft_content
            )
            return api_response(True, "", ContentLandingPageSerializer(page).data)
