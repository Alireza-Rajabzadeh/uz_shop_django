from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import UUID, uuid4

from .client import DigikalaClient
from .contracts import ApprovedCategory, ListingOptions, detail_url, validate_mappings
from .detail import normalize_detail
from .filesystem import read_json, sha256_json, write_json_atomic
from .listing import category_summary, extract_product_payloads, find_total_pages, normalize_listing_product, page_url


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]


class CollectionCancelled(RuntimeError):
    pass


def _notify(callback: ProgressCallback | None, **event: Any) -> None:
    if callback:
        callback(event)


def _check_cancel(callback: CancelCallback | None) -> None:
    if callback and callback():
        raise CollectionCancelled("collection cancelled")


def collect_listings(
    mappings: Iterable[ApprovedCategory | dict[str, Any]],
    options: ListingOptions,
    output_path: str | Path,
    *,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
    client: DigikalaClient | None = None,
) -> dict[str, Any]:
    categories = validate_mappings(mappings)
    http = client or DigikalaClient(
        timeout=options.timeout, retries=options.retries, delay=options.delay
    )
    products: dict[int, dict[str, Any]] = {}
    summaries = []
    for category_index, category in enumerate(categories, start=1):
        seen: set[int] = set()
        page = 1
        total_pages: int | None = None
        exhausted = False
        while len(seen) < options.products_per_category:
            _check_cancel(cancel)
            if total_pages is not None and page > total_pages:
                exhausted = True
                break
            response = http.get_listing(page_url(category.api_url, page))
            if total_pages is None:
                total_pages = find_total_pages(response)
            payloads = extract_product_payloads(response)
            if not payloads:
                exhausted = True
                break
            added = 0
            page_seen: set[int] = set()
            for payload in payloads:
                try:
                    normalized = normalize_listing_product(payload)
                except (KeyError, TypeError, ValueError):
                    continue
                product_id = normalized["product_id"]
                if product_id in page_seen:
                    continue
                page_seen.add(product_id)
                if normalized["is_ad"] and not options.include_ads:
                    continue
                if product_id in seen:
                    continue
                seen.add(product_id)
                added += 1
                aggregate = products.setdefault(product_id, normalized)
                if category.category_id not in aggregate["category_ids"]:
                    aggregate["category_ids"].append(category.category_id)
                if len(seen) >= options.products_per_category:
                    break
            _notify(
                progress,
                phase="listings",
                category_index=category_index,
                category_count=len(categories),
                category_id=category.category_id,
                page=page,
                widgets=len(page_seen),
                added=added,
                collected=len(seen),
            )
            page += 1
            if len(seen) < options.products_per_category:
                getattr(http, "sleep", lambda _seconds: None)(options.delay)
            if added == 0 and total_pages is None:
                exhausted = True
                break
        summaries.append(category_summary(category, len(seen), page - 1, exhausted))

    ordered_products = [products[key] for key in sorted(products)]
    for product in ordered_products:
        product["category_ids"].sort()
    document = {
        "schema": "uzshop.digikala.listing/v1",
        "listing_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": "digikala", "currency": "IRR"},
        "options": options.as_dict(),
        "categories": summaries,
        "products": ordered_products,
        "summary": {
            "category_count": len(categories),
            "unique_product_count": len(ordered_products),
            "category_product_count": sum(item["collected"] for item in summaries),
        },
    }
    document["sha256"] = sha256_json(document)
    write_json_atomic(output_path, document)
    return document


def validate_listing_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != "uzshop.digikala.listing/v1":
        raise ValueError("not a Digikala listing/v1 document")
    checksum = document.get("sha256")
    unsigned = {key: value for key, value in document.items() if key != "sha256"}
    if not isinstance(checksum, str) or checksum != sha256_json(unsigned):
        raise ValueError("listing SHA-256 is missing or invalid")
    try:
        UUID(str(document.get("listing_id")))
    except (TypeError, ValueError) as error:
        raise ValueError("listing_id must be a UUID") from error
    source = document.get("source")
    if not isinstance(source, dict) or source.get("currency") != "IRR":
        raise ValueError("listing source currency must be IRR")
    categories = document.get("categories")
    if not isinstance(categories, list) or not 1 <= len(categories):
        raise ValueError("listing must contain at least one category summary")
    products = document.get("products")
    if not isinstance(products, list):
        raise ValueError("listing products must be a list")
    try:
        product_ids = [int(product["product_id"]) for product in products]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("listing products must have valid product IDs") from error
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("listing product IDs must be globally unique")
    return document


def collect_details(
    listing_path: str | Path,
    output_dir: str | Path,
    *,
    product_ids: Iterable[int] | None = None,
    timeout: int = 30,
    retries: int = 3,
    delay: float = 1.0,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
    client: DigikalaClient | None = None,
) -> list[Path]:
    listing = validate_listing_document(read_json(listing_path))
    available = {int(product["product_id"]) for product in listing["products"]}
    selected = sorted(available if product_ids is None else {int(value) for value in product_ids})
    unknown = set(selected) - available
    if unknown:
        raise ValueError(f"product IDs are not in listing: {sorted(unknown)}")
    http = client or DigikalaClient(timeout=timeout, retries=retries, delay=delay)
    destination = Path(output_dir)
    written = []
    for index, product_id in enumerate(selected, start=1):
        _check_cancel(cancel)
        payload = http.get_detail(detail_url(product_id), expected_product_id=product_id)
        normalized = normalize_detail(payload, product_id)
        normalized["listing_id"] = listing["listing_id"]
        path = destination / f"{product_id}.json"
        write_json_atomic(path, normalized)
        written.append(path)
        _notify(progress, phase="details", index=index, count=len(selected), product_id=product_id)
        if index < len(selected):
            getattr(http, "sleep", lambda _seconds: None)(delay)
    return written
