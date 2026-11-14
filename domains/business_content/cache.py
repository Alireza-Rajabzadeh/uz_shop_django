from core.services import CacheService


HOME_CACHE_KEY = "business-content:home"


def home_cache_key(business_id=None):
    if business_id is not None:
        return f"business-content:home:{business_id}"
    return HOME_CACHE_KEY


def landing_page_cache_key(slug, business_id=None):
    if business_id is not None:
        return f"business-content:landing-pages:{slug}:{business_id}"
    return f"business-content:landing-pages:{slug}"


def page_cache_key(slug, business_id=None):
    if business_id is not None:
        return f"business-content:pages:{slug}:{business_id}"
    return f"business-content:pages:{slug}"


def invalidate_landing_page(slug, business_id=None):
    CacheService().delete_public(landing_page_cache_key(slug))
    if business_id is not None:
        CacheService().delete_public(landing_page_cache_key(slug, business_id))


def invalidate_page(slug, business_id=None):
    cache = CacheService()
    cache.delete_public(page_cache_key(slug))
    if business_id is not None:
        cache.delete_public(page_cache_key(slug, business_id))
    if slug == "home":
        cache.delete_public(HOME_CACHE_KEY)
        if business_id is not None:
            cache.delete_public(home_cache_key(business_id))
