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


def layout_cache_key(business_id=None) -> str:
    """Build the storefront layout cache key.

    Format:
    - storefront:layout:{business_id} (tenant context)
    - storefront:layout:platform (platform context)
    """
    if business_id is not None:
        bid = getattr(business_id, "id", business_id)
        return f"storefront:layout:{bid}"
    return "storefront:layout:platform"


def invalidate_layout_cache(business_id=None) -> bool:
    """Invalidate cached storefront layout."""
    return CacheService().delete_public(layout_cache_key(business_id=business_id))
