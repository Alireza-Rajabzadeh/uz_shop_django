from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from core.services import CacheService
from domains.business.services.business_subdomain_service import (
    BusinessSubdomainService,
)
from domains.storefront.services.layout_service import StorefrontLayoutService

from ..cache import LAYOUT_CACHE_TTL, layout_cache_key


class StorefrontLayoutView(APIView):
    """Customer-facing storefront layout API.

    Resolves and returns shared layout configuration (header, categories, footer, theme, config)
    for the resolved tenant or the platform storefront using the business subdomain.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        subdomain = request.headers.get("X-Tenant-Subdomain") or request.query_params.get("subdomain")
        if subdomain:
            subdomain = subdomain.strip().lower()

        cache = CacheService()

        # Platform context (no subdomain provided)
        if not subdomain:
            cache_key = layout_cache_key()
            cached = cache.get_public(cache_key)
            if cached is not None:
                return api_response(True, "", cached)

            data = StorefrontLayoutService().resolve_layout(business=None)
            data["status"] = "ACTIVE"
            data["subdomain"] = None
            cache.put_public(cache_key, data, ttl=LAYOUT_CACHE_TTL)
            return api_response(True, "", data)

        # Tenant context: check cache using subdomain as the cache key
        cache_key = layout_cache_key(subdomain=subdomain)
        cached = cache.get_public(cache_key)
        if cached is not None:
            return api_response(True, "", cached)

        # Cache miss: resolve subdomain
        resolution = BusinessSubdomainService.resolve_subdomain(subdomain)
        status = resolution.get("status")

        # Scenario 1: Active Subdomain
        if status == "ACTIVE":
            business = resolution.get("business")
            data = StorefrontLayoutService().resolve_layout(business=business)
            data["status"] = "ACTIVE"
            data["subdomain"] = resolution.get("subdomain", subdomain)
            cache.put_public(cache_key, data, ttl=LAYOUT_CACHE_TTL)
            return api_response(True, "", data)

        # Scenario 2: Historical Subdomain (REDIRECT)
        if status == "REDIRECT":
            canonical_subdomain = resolution.get("canonical_subdomain")
            redirect_data = {
                "status": "REDIRECT",
                "subdomain": subdomain,
                "canonical_subdomain": canonical_subdomain,
            }
            res = api_response(
                False,
                "Subdomain has moved.",
                data=redirect_data,
                errors={"detail": "Subdomain has moved."},
                status_code=308,
            )
            if canonical_subdomain:
                res["X-Canonical-Subdomain"] = canonical_subdomain
            return res

        # Scenario 3: Unknown / Invalid / Reserved Subdomain
        platform_domain = getattr(settings, "PLATFORM_DOMAIN", "charchu.com")
        unknown_data = {
            "status": "UNKNOWN",
            "subdomain": subdomain,
            "platform_domain": platform_domain,
        }
        return api_response(
            False,
            "Subdomain does not exist.",
            data=unknown_data,
            errors={"detail": "Subdomain does not exist."},
            status_code=404,
        )
