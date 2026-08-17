from core.services import CacheService
from domains.catalog.services import CategoryService

from .storefront_serializers import StorefrontStaticCategorySerializer

cache_service = CacheService()


def get_categories_static_data():
    categories = CategoryService().get_storefront_tree()
    data = StorefrontStaticCategorySerializer(categories, many=True).data
    cache_service.put_public("categories", data)
    return data


STATIC_DATA_HANDLERS = {
    "categories": get_categories_static_data,
}
