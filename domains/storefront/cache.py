from core.services import CacheService

LAYOUT_CACHE_TTL = 300


def page_cache_key(slug: str, business_id=None) -> str:
    """Build the storefront page cache key.

    Format:
    - storefront:page:{slug}:{business_id} (tenant context)
    - storefront:page:{slug}:platform (platform context)
    """
    if business_id is not None:
        bid = getattr(business_id, "id", business_id)
        return f"storefront:page:{slug}:{bid}"
    return f"storefront:page:{slug}:platform"


def invalidate_page_cache(slug: str, business_id=None) -> bool:
    """Invalidate cached storefront page."""
    return CacheService().delete_public(page_cache_key(slug, business_id=business_id))


def layout_cache_key(subdomain: str | None = None, business_id=None) -> str:
    """Build the storefront layout cache key.

    Format:
    - storefront:layout:{subdomain} (tenant context)
    - storefront:layout:platform (platform context)
    """
    if subdomain:
        clean = subdomain.strip().lower()
        return f"storefront:layout:{clean}"
    if business_id is not None:
        from domains.business.models import BusinessProfile
        from domains.business.services.business_subdomain_service import (
            BusinessSubdomainService,
        )

        biz = BusinessProfile.objects.filter(
            id=getattr(business_id, "id", business_id)
        ).first()
        active_sub = BusinessSubdomainService.get_active_subdomain(biz)
        if active_sub and active_sub.subdomain:
            return f"storefront:layout:{active_sub.subdomain.strip().lower()}"
    return "storefront:layout:platform"


def invalidate_layout_cache(subdomain: str | None = None, business_id=None) -> bool:
    """Invalidate cached storefront layout."""
    return CacheService().delete_public(
        layout_cache_key(subdomain=subdomain, business_id=business_id)
    )
