import json
import logging
import time

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


class CacheService:
    cache_alias = "application_cache"

    # Single-flight rebuild tuning. The wait has to outlast a page rebuild
    # for concurrent misses to collapse into one request, and stay short
    # enough that a payload which is never cached costs no latency.
    REBUILD_LOCK_TTL = 10
    REBUILD_POLL_INTERVAL = 0.05
    REBUILD_POLL_ATTEMPTS = 10

    def __init__(self, connection=None):
        self.connection = connection or get_redis_connection(self.cache_alias)

    def get(self, key):
        try:
            value = self.connection.get(key)
        except Exception:
            logger.warning("Cache read failed.", exc_info=True)
            return None
        if value is None:
            return None
        try:
            if isinstance(value, bytes):
                value = value.decode()
            return json.loads(value)
        except (TypeError, ValueError, UnicodeDecodeError):
            logger.warning("Discarding malformed cached JSON.", exc_info=True)
            return None

    def get_public(self, key):
        return self.get(self._cache_key(settings.CACHE_PUBLIC_PREFIX, key))

    def put_public(self, key, data, ttl=None):
        cache_key = self._cache_key(settings.CACHE_PUBLIC_PREFIX, key)
        if ttl is None:
            return self._put(cache_key, data)
        return self._put(cache_key, data, ttl=ttl)

    def put_private(self, key, data):
        return self._put(self._cache_key(settings.CACHE_PRIVATE_PREFIX, key), data)

    def delete_public(self, key):
        try:
            self.connection.delete(self._cache_key(settings.CACHE_PUBLIC_PREFIX, key))
        except Exception:
            logger.warning("Cache delete failed.", exc_info=True)
            return False
        return True

    def get_or_set_public(self, key, builder, ttl=None):
        """Read a public key, rebuilding it once across concurrent misses.

        ``builder`` returns the payload and, optionally, its own TTL:

        - ``builder() -> data`` caches the result with ``ttl``
        - ``builder() -> (data, ttl)`` decides per call; ``None`` or ``0``
          leaves the payload out of Redis without failing the request

        Only one caller rebuilds at a time. The others wait for that value,
        and when the winner finishes without caching they build for
        themselves instead of waiting out the whole poll window. Redis is
        never required here: a failed lock, wait, or write degrades into a
        plain build.
        """
        cached = self.get_public(key)
        if cached is not None:
            return cached

        if self._acquire_rebuild_lock(key):
            try:
                built = builder()
                data, built_ttl = built if isinstance(built, tuple) else (built, ttl)
                if built_ttl is not None and built_ttl > 0:
                    self.put_public(key, data, ttl=built_ttl)
                return data
            finally:
                self._release_rebuild_lock(key)

        waiting = self._wait_for_rebuild(key)
        if waiting is not None:
            return waiting
        return builder()

    def _acquire_rebuild_lock(self, key):
        try:
            acquired = self.connection.set(
                self._rebuild_lock_key(key), b"1", nx=True, ex=self.REBUILD_LOCK_TTL
            )
        except Exception:
            logger.warning("Cache rebuild lock failed.", exc_info=True)
            return False
        return bool(acquired)

    def _release_rebuild_lock(self, key):
        try:
            self.connection.delete(self._rebuild_lock_key(key))
        except Exception:
            logger.warning("Cache rebuild unlock failed.", exc_info=True)

    def _wait_for_rebuild(self, key):
        """Return the winning rebuild's payload, or ``None`` if waiting will not help."""
        for _ in range(self.REBUILD_POLL_ATTEMPTS):
            value = self.get_public(key)
            if value is not None:
                return value
            if not self._rebuild_lock_exists(key):
                # The rebuild finished without caching anything, so only
                # waiting out the poll window would delay this caller's own
                # build — which is exactly what `cache_ttl = 0` asks for.
                return None
            time.sleep(self.REBUILD_POLL_INTERVAL)
        return None

    def _rebuild_lock_exists(self, key):
        try:
            return bool(self.connection.exists(self._rebuild_lock_key(key)))
        except Exception:
            logger.warning("Cache rebuild lock probe failed.", exc_info=True)
            return False

    def _rebuild_lock_key(self, key):
        # Under the private prefix so the storefront's read-only ACL user,
        # which is limited to `public:*`, can never observe the lock.
        return self._cache_key(
            settings.CACHE_PRIVATE_PREFIX, f"{key}:rebuild-lock"
        )

    def _put(self, cache_key, data, ttl=None):
        value = json.dumps(
            data,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        try:
            if ttl is not None and ttl > 0:
                self.connection.set(cache_key, value, ex=ttl)
            else:
                self.connection.set(cache_key, value)
        except Exception:
            logger.warning("Cache write failed.", exc_info=True)
            return False
        return True

    @staticmethod
    def _cache_key(prefix, key):
        return f"{prefix}:{key}"
