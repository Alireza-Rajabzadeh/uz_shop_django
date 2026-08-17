import json
import logging

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


class CacheService:
    cache_alias = "application_cache"

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

    def put_public(self, key, data):
        return self._put(self._cache_key(settings.CACHE_PUBLIC_PREFIX, key), data)

    def put_private(self, key, data):
        return self._put(self._cache_key(settings.CACHE_PRIVATE_PREFIX, key), data)

    def _put(self, cache_key, data):
        value = json.dumps(
            data,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        try:
            self.connection.set(cache_key, value)
        except Exception:
            logger.warning("Cache write failed.", exc_info=True)
            return False
        return True

    @staticmethod
    def _cache_key(prefix, key):
        return f"{prefix}:{key}"
