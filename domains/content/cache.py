from core.services import CacheService


HOME_CACHE_KEY = "content:home"


def landing_page_cache_key(slug):
    return f"content:landing-pages:{slug}"


def page_cache_key(slug):
    return f"content:pages:{slug}"


def invalidate_landing_page(slug):
    CacheService().delete_public(landing_page_cache_key(slug))


def invalidate_page(slug):
    cache = CacheService()
    cache.delete_public(page_cache_key(slug))
    if slug == "home":
        cache.delete_public(HOME_CACHE_KEY)
