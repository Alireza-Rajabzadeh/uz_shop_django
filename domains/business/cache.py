from core.services import CacheService

BUSINESS_CACHE_KEY = "business:data"


def invalidate_business_cache():
    CacheService().delete_public(BUSINESS_CACHE_KEY)
