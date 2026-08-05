from django.conf import settings
from django.utils.module_loading import import_string

from .contracts import ProductSearchCriteria, ProductSearchResult


class StorefrontSearchService:
    def __init__(self, backend=None):
        if backend is None:
            backend_class = import_string(settings.CATALOG_SEARCH_BACKEND)
            backend = backend_class()
        self.backend = backend

    def search(self, criteria: ProductSearchCriteria) -> ProductSearchResult:
        return self.backend.search(criteria)
