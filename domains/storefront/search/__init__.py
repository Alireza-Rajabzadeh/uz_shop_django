from .contracts import (
    FacetSelection,
    ProductSearchBackend,
    ProductSearchCriteria,
    ProductSearchResult,
)
from .normalization import normalize_search_text
from .postgres import PostgresProductSearchBackend
from .service import StorefrontSearchService

__all__ = [
    "FacetSelection",
    "ProductSearchBackend",
    "ProductSearchCriteria",
    "ProductSearchResult",
    "PostgresProductSearchBackend",
    "StorefrontSearchService",
    "normalize_search_text",
]
