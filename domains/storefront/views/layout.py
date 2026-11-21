from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
from domains.storefront.services.layout_service import StorefrontLayoutService

from ..cache import LAYOUT_CACHE_TTL, layout_cache_key


class StorefrontLayoutView(APIView):
    """Customer-facing storefront layout API.

    Returns shared layout configuration (header, categories, footer, theme, config)
    for the resolved tenant or the platform storefront.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        business = getattr(request, "business", None)
        cache_key = layout_cache_key(business_id=business)

        cache = CacheService()
        cached = cache.get_public(cache_key)
        if cached is not None:
            return api_response(True, "", cached)

        data = StorefrontLayoutService().resolve_layout(business=business)
        cache.put_public(cache_key, data, ttl=LAYOUT_CACHE_TTL)

        return api_response(True, "", data)
