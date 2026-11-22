from django.conf import settings
from django.utils.module_loading import import_string

from .contracts import ProductSearchCriteria, ProductSearchResult


class StorefrontSearchService:
    def __init__(self, backend=None):
        if backend is None:
            backend_path = getattr(
                settings,
                "STOREFRONT_SEARCH_BACKEND",
                getattr(
                    settings,
                    "CATALOG_SEARCH_BACKEND",
                    "domains.storefront.search.postgres.PostgresProductSearchBackend",
                ),
            )
            backend_class = import_string(backend_path)
            backend = backend_class()
        self.backend = backend

    def search(self, criteria: ProductSearchCriteria) -> ProductSearchResult:
        return self.backend.search(criteria)
