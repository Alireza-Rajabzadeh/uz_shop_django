from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit
import re

from .filesystem import read_json


API_HOST = "api.digikala.com"
LISTING_PATH = re.compile(r"^/discovery/api/v2/categories/(\d+)/products/?$")
DETAIL_PATH = re.compile(r"^/v2/product/(\d+)/?$")


class ValidationError(ValueError):
    pass


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field} must be a positive integer") from error
    if result < 1:
        raise ValidationError(f"{field} must be a positive integer")
    return result


def validate_api_url(url: str, pattern: re.Pattern[str], field: str) -> int:
    if not isinstance(url, str):
        raise ValidationError(f"{field} must be a URL")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != API_HOST
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise ValidationError(f"{field} must use https://{API_HOST}")
    match = pattern.fullmatch(parts.path)
    if not match:
        raise ValidationError(f"{field} has an unexpected path")
    return int(match.group(1))


@dataclass(frozen=True)
class ListingOptions:
    products_per_category: int = 20
    currency: str = "IRR"
    timeout: int = 30
    retries: int = 3
    delay: float = 1.0
    include_ads: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.products_per_category, int) or isinstance(self.products_per_category, bool) or not 1 <= self.products_per_category <= 100:
            raise ValidationError("products_per_category must be between 1 and 100")
        if self.currency != "IRR":
            raise ValidationError("currency must be IRR")
        if not isinstance(self.timeout, int) or isinstance(self.timeout, bool) or not 1 <= self.timeout <= 60:
            raise ValidationError("timeout must be between 1 and 60 seconds")
        if not isinstance(self.retries, int) or isinstance(self.retries, bool) or not 1 <= self.retries <= 5:
            raise ValidationError("retries must be between 1 and 5")
        if isinstance(self.delay, bool) or not isinstance(self.delay, (int, float)) or self.delay < 0.5:
            raise ValidationError("delay must be at least 0.5 seconds")
        if not isinstance(self.include_ads, bool):
            raise ValidationError("include_ads must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovedCategory:
    category_id: int
    name: str
    digikala_category_id: int
    api_url: str

    @classmethod
    def from_dict(cls, value: Any) -> "ApprovedCategory":
        if not isinstance(value, dict):
            raise ValidationError("each approved category must be an object")
        category_id = _positive_int(value.get("category_id"), "category_id")
        digikala_id = _positive_int(
            value.get("digikala_category_id"), "digikala_category_id"
        )
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("name must be a non-empty string")
        api_url = value.get("api_url")
        path_id = validate_api_url(api_url, LISTING_PATH, "api_url")
        if path_id != digikala_id:
            raise ValidationError("api_url category ID does not match digikala_category_id")
        return cls(category_id, name.strip(), digikala_id, api_url)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_mappings(values: Iterable[Any]) -> list[ApprovedCategory]:
    mappings = [
        value if isinstance(value, ApprovedCategory) else ApprovedCategory.from_dict(value)
        for value in values
    ]
    if not mappings:
        raise ValidationError("at least one approved category is required")
    local_ids = [item.category_id for item in mappings]
    if len(local_ids) != len(set(local_ids)):
        raise ValidationError("category_id values must be unique")
    return mappings


def load_approved_mapping(path: str | Path) -> list[ApprovedCategory]:
    data = read_json(path)
    values = data.get("categories") if isinstance(data, dict) else data
    if not isinstance(values, list):
        raise ValidationError('approved mapping must be a list or contain a "categories" list')
    return validate_mappings(values)


def detail_url(product_id: Any) -> str:
    return f"https://{API_HOST}/v2/product/{_positive_int(product_id, 'product_id')}/"


def validate_detail_url(url: str, expected_product_id: int | None = None) -> int:
    product_id = validate_api_url(url, DETAIL_PATH, "detail URL")
    if expected_product_id is not None and product_id != expected_product_id:
        raise ValidationError("detail URL product ID does not match expected product ID")
    return product_id
