from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
from domains.business_content.services import PageService as BusinessPageService
from domains.content.services import PageService as ContentPageService

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
            return api_response(True, "", cached)

        if business is not None:
            data, ttl = BusinessPageService().get_storefront_page(
                slug=slug, business=business
            )
        else:
            data, ttl = ContentPageService().get_storefront_page(slug=slug)

        if ttl is None or ttl > 0:
            cache.put_public(cache_key, data, ttl=ttl)

        return api_response(True, "", data)
