from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class FacetSelection:
    field_id: int
    value_ids: tuple[int, ...]


@dataclass(frozen=True)
class ProductSearchCriteria:
    query: str = ""
    category_ids: tuple[int, ...] = ()
    brand_ids: tuple[int, ...] = ()
    detail_filters: tuple[FacetSelection, ...] = ()
    variant_filters: tuple[FacetSelection, ...] = ()
    minimum_price: Decimal | None = None
    maximum_price: Decimal | None = None
    in_stock: bool | None = None
    on_sale: bool | None = None
    ordering: str = "relevance"
    page: int = 1
    page_size: int = 24
    include_facets: bool = True


@dataclass(frozen=True)
class ProductSearchResult:
    count: int
    page: int
    page_size: int
    results: list[dict[str, Any]]
    facets: dict[str, Any] = field(default_factory=dict)


class ProductSearchBackend(Protocol):
    def search(self, criteria: ProductSearchCriteria) -> ProductSearchResult: ...
