from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .contracts import ApprovedCategory


def page_url(url: str, page: int) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key not in {"_rch", "page"}]
    query.append(("page", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def extract_product_payloads(value: Any) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            data = node.get("data")
            if node.get("type") == "product" and isinstance(data, dict) and data.get("id") is not None:
                products.append(data)
                return
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return products


def find_total_pages(value: Any) -> int | None:
    pager_pages: list[int] = []
    tracker_pages: list[int] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            pager = node.get("pager")
            if isinstance(pager, dict) and isinstance(pager.get("total_pages"), int):
                pager_pages.append(pager["total_pages"])
            tracker = node.get("tracker_data")
            if isinstance(tracker, dict) and isinstance(tracker.get("total_pages"), int):
                tracker_pages.append(tracker["total_pages"])
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    if pager_pages:
        return max(pager_pages)
    return max(tracker_pages) if tracker_pages else None


def _first_url(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, str) and item), None)
    return None


def normalize_listing_product(payload: dict[str, Any]) -> dict[str, Any]:
    product_id = int(payload["id"])
    images = payload.get("images") if isinstance(payload.get("images"), dict) else {}
    main = images.get("main") if isinstance(images.get("main"), dict) else {}
    variant = payload.get("default_variant") if isinstance(payload.get("default_variant"), dict) else {}
    properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    url = payload.get("url") if isinstance(payload.get("url"), dict) else {}
    brand = payload.get("brand") if isinstance(payload.get("brand"), dict) else {}
    return {
        "product_id": product_id,
        "category_ids": [],
        "title_fa": payload.get("title_fa"),
        "title_en": payload.get("title_en"),
        "url": url.get("uri"),
        "status": payload.get("status"),
        "brand": {
            "id": brand.get("id"),
            "code": brand.get("code"),
            "title_fa": brand.get("title_fa"),
            "title_en": brand.get("title_en"),
        },
        "image_url": _first_url(main.get("url")),
        "image_webp_url": _first_url(main.get("webp_url")),
        "rating": payload.get("rating"),
        "colors": payload.get("colors") if isinstance(payload.get("colors"), list) else [],
        "is_ad": bool(properties.get("is_ad")),
        "default_variant": {
            key: variant.get(key)
            for key in (
                "id", "title", "status", "rate", "lead_time", "order_limit",
                "marketable_stock", "color", "themes", "price",
            )
        },
    }


def category_summary(category: ApprovedCategory, collected: int, pages: int, exhausted: bool) -> dict[str, Any]:
    return {
        **category.as_dict(),
        "collected": collected,
        "pages_fetched": pages,
        "exhausted": exhausted,
    }
