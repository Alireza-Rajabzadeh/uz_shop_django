from core.services import CacheService

CATEGORIES_CACHE_KEY = "categories"

# Bounded staleness for the storefront category tree. Category writes drop
# the key through `signals.py`; this TTL is the safety net for writers that
# never reach a `post_save` — the `seed_categories` command and bulk
# querysets — and for keys written before invalidation existed.
CATEGORIES_CACHE_TTL = 300


def invalidate_categories_cache() -> bool:
    """Drop the shared storefront category tree.

    The panels read this key straight from Redis and only fall back to
    `/api/catalog/statics` when it is missing, so a key with no expiry
    would keep serving whatever was first built until a Redis flush.
    """
    return CacheService().delete_public(CATEGORIES_CACHE_KEY)
