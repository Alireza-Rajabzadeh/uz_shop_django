from django.conf import settings
from core.services import CacheService

BUSINESS_CACHE_KEY = "business:data"


def invalidate_business_cache(business_id=None):
    cache = CacheService()
    cache.delete_public(BUSINESS_CACHE_KEY)
    if business_id:
        cache.delete_public(f"{BUSINESS_CACHE_KEY}:{business_id}")
    else:
        try:
            pattern = cache._cache_key(settings.CACHE_PUBLIC_PREFIX, f"{BUSINESS_CACHE_KEY}:*")
            keys = cache.connection.keys(pattern)
            if keys:
                cache.connection.delete(*keys)
        except Exception:
            pass
