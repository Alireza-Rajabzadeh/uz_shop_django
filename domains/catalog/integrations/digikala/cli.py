from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .contracts import ListingOptions, ValidationError, load_approved_mapping
from .discovery import discover_categories
from .filesystem import read_json
from .pipeline import CollectionCancelled, collect_details, collect_listings, validate_listing_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect validated Digikala catalog data.")
    commands = parser.add_subparsers(dest="command", required=True)

    discovery = commands.add_parser(
        "discover", help="Discover approved API mappings for up to five leaf categories."
    )
    discovery.add_argument("--categories", required=True)
    discovery.add_argument("--category-id", type=int, action="append", required=True)
    discovery.add_argument("--output", required=True)
    discovery.add_argument("--chromium-path")
    discovery.add_argument("--headful", action="store_true")
    _network_arguments(discovery)

    listings = commands.add_parser("listings", help="Collect a finalized listing document.")
    listings.add_argument("--mapping", required=True)
    listings.add_argument("--output", required=True)
    _network_arguments(listings)
    listings.add_argument("--products-per-category", type=int, default=20)
    listings.add_argument("--include-ads", action="store_true")

    details = commands.add_parser("details", help="Collect normalized product details.")
    details.add_argument("--listing", required=True)
    details.add_argument("--output-dir", required=True)
    details.add_argument("--product-id", type=int, action="append", dest="product_ids")
    _network_arguments(details)

    validate = commands.add_parser("validate", help="Validate an approved mapping or listing.")
    group = validate.add_mutually_exclusive_group(required=True)
    group.add_argument("--mapping")
    group.add_argument("--listing")
    return parser


def _network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)


def _progress(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover":
            mappings = discover_categories(
                args.categories,
                args.category_id,
                args.output,
                chromium_path=args.chromium_path,
                headful=args.headful,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                progress=_progress,
            )
            print(f"Wrote {len(mappings)} approved mappings to {args.output}")
            return 0
        if args.command == "validate":
            if args.mapping:
                count = len(load_approved_mapping(args.mapping))
                print(f"Valid approved mapping: {count} categories")
            else:
                listing = validate_listing_document(read_json(args.listing))
                print(f"Valid listing: {len(listing['products'])} products")
            return 0
        if args.command == "listings":
            options = ListingOptions(
                products_per_category=args.products_per_category,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                include_ads=args.include_ads,
            )
            result = collect_listings(
                load_approved_mapping(args.mapping), options, args.output, progress=_progress
            )
            print(f"Wrote {len(result['products'])} products to {args.output}")
            return 0
        ListingOptions(timeout=args.timeout, retries=args.retries, delay=args.delay)
        paths = collect_details(
            args.listing,
            args.output_dir,
            product_ids=args.product_ids,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
            progress=_progress,
        )
        print(f"Wrote {len(paths)} detail files to {Path(args.output_dir)}")
        return 0
    except CollectionCancelled:
        print("Collection cancelled", file=sys.stderr)
        return 130
    except (FileNotFoundError, FileExistsError, ValidationError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
