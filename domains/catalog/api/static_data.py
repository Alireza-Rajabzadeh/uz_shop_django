from core.services import CacheService
from domains.catalog.cache import CATEGORIES_CACHE_KEY, CATEGORIES_CACHE_TTL
from domains.catalog.services import CategoryService

from .storefront_serializers import StorefrontStaticCategorySerializer

cache_service = CacheService()


def get_categories_static_data():
    categories = CategoryService().get_storefront_tree()
    data = StorefrontStaticCategorySerializer(categories, many=True).data
    cache_service.put_public(CATEGORIES_CACHE_KEY, data, ttl=CATEGORIES_CACHE_TTL)
    return data


STATIC_DATA_HANDLERS = {
    "categories": get_categories_static_data,
}
