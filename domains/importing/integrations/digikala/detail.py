from __future__ import annotations

from html import unescape
import re
from typing import Any

from .contracts import detail_url


TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _plain_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = SPACE.sub(" ", unescape(TAG.sub(" ", value))).strip()
    return text or None


def _urls(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_urls(item))
        return list(dict.fromkeys(result))
    if isinstance(value, dict):
        result = []
        for key in ("url", "webp_url"):
            result.extend(_urls(value.get(key)))
        return list(dict.fromkeys(result))
    return []


def _named(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "id": value.get("id"),
        "code": value.get("code"),
        "title_fa": value.get("title_fa") or value.get("title"),
        "title_en": value.get("title_en"),
    }


def _specifications(product: dict[str, Any]) -> list[dict[str, Any]]:
    source = product.get("specifications") or product.get("specification")
    groups = _list(source)
    if isinstance(source, dict):
        groups = _list(source.get("groups") or source.get("items"))
    result = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        attributes = []
        for attribute in _list(group.get("attributes") or group.get("items")):
            if not isinstance(attribute, dict):
                continue
            raw_values = attribute.get("values", attribute.get("value"))
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            attributes.append(
                {
                    "id": attribute.get("id"),
                    "title": attribute.get("title") or attribute.get("name"),
                    "values": [value for value in values if value is not None],
                }
            )
        result.append(
            {
                "id": group.get("id"),
                "title": group.get("title") or group.get("name"),
                "attributes": attributes,
            }
        )
    return result


def _variants(product: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    source = _list(product.get("variants"))
    if not source and isinstance(product.get("default_variant"), dict):
        source = [product["default_variant"]]
    for variant in source:
        if not isinstance(variant, dict):
            continue
        result.append(
            {
                "id": variant.get("id"),
                "title": variant.get("title"),
                "status": variant.get("status"),
                "themes": _list(variant.get("themes")),
                "color": _named(variant.get("color")),
                "price": _dict(variant.get("price")),
                "stock": {
                    "marketable": variant.get("marketable_stock"),
                    "seller": variant.get("seller_stock"),
                    "order_limit": variant.get("order_limit"),
                    "lead_time": variant.get("lead_time"),
                },
                "seller": _named(variant.get("seller")),
                "warranty": _named(variant.get("warranty")),
            }
        )
    return result


def normalize_detail(payload: Any, expected_product_id: int | None = None) -> dict[str, Any]:
    root = _dict(payload)
    data = _dict(root.get("data"))
    product = _dict(data.get("product")) or _dict(root.get("product")) or data or root
    try:
        product_id = int(product.get("id"))
    except (TypeError, ValueError) as error:
        raise ValueError("detail payload has no valid product ID") from error
    if expected_product_id is not None and product_id != int(expected_product_id):
        raise ValueError("detail payload product ID does not match requested product ID")

    images = _dict(product.get("images"))
    category_source = _dict(product.get("category"))
    category = _named(category_source)
    breadcrumb_source = (
        product.get("breadcrumb")
        or product.get("breadcrumbs")
        or category_source.get("breadcrumb")
        or category_source.get("breadcrumbs")
    )
    breadcrumbs = [item for item in (_named(value) for value in _list(breadcrumb_source)) if item]
    return {
        "source": {"id": product_id, "url": detail_url(product_id)},
        "title_fa": product.get("title_fa"),
        "title_en": product.get("title_en"),
        "description": _plain_text(product.get("description")),
        "brand": _named(product.get("brand")),
        "category": category,
        "breadcrumb": breadcrumbs,
        "specifications": _specifications(product),
        "variants": _variants(product),
        "images": {
            "main": _urls(images.get("main")),
            "gallery": _urls(images.get("list") or images.get("gallery")),
        },
        "raw_status": product.get("status"),
    }
