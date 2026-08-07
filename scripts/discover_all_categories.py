#!/usr/bin/env python3
"""Auto-discover Digikala API mappings for every leaf category.

Runs the existing ``discover_categories`` workflow in adaptive chunks so a
single problematic category never discards the whole run: failing chunks are
split in half until they succeed at single-category granularity. Every
successful mapping is merged into the canonical approved mapping file.

Requires Playwright + Chromium and internet access to digikala.com:

    pip install -r scripts/requirements-digikala-discovery.txt
    python scripts/discover_all_categories.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domains.catalog.integrations.digikala.discovery import discover_categories  # noqa: E402
from domains.catalog.integrations.digikala.filesystem import read_json  # noqa: E402


def leaf_category_ids(manifest: dict) -> list[int]:
    ids: list[int] = []

    def visit(items):
        for item in items:
            if item.get("children"):
                visit(item["children"])
            else:
                ids.append(int(item["id"]))

    visit(manifest.get("categories", []))
    return ids


def merge_mapping(output_path: Path, documents: list[dict]) -> None:
    if output_path.exists():
        existing = read_json(output_path) or {}
    else:
        existing = {}
    categories = list(existing.get("categories", []))
    seen: set[int] = {
        int(entry["category_id"])
        for entry in categories
        if isinstance(entry, dict) and entry.get("category_id") is not None
    }
    for document in documents:
        for entry in document.get("categories", []):
            category_id = entry["category_id"]
            if category_id in seen:
                continue
            seen.add(category_id)
            categories.append(entry)
    payload = {"schema": "uzshop.digikala.category-mappings/v1", "categories": categories}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args) -> int:
    manifest_path = Path(args.category_manifest).resolve()
    output_path = Path(args.output).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_ids = leaf_category_ids(manifest)
    if not all_ids:
        print("No leaf categories found in the canonical manifest.", file=sys.stderr)
        return 2

    print(f"Discovered {len(all_ids)} leaf categories to map.", file=sys.stderr)
    pending = list(all_ids)
    successes: list[dict] = []
    failures: list[int] = []

    def discover_chunk(chunk, output: Path) -> dict:
        discover_categories(
            manifest_path,
            chunk,
            output,
            chromium_path=args.chromium_path,
            headful=args.headful,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
        )
        return read_json(output)

    def collect(chunk: list[int]) -> None:
        if not chunk:
            return
        with tempfile.TemporaryDirectory() as directory:
            batch_output = Path(directory) / "batch.json"
            try:
                document = discover_chunk(chunk, batch_output)
            except Exception as exc:
                print(f"  chunk {chunk} failed: {exc}", file=sys.stderr)
                if len(chunk) <= 1:
                    failures.extend(chunk)
                    return
                mid = len(chunk) // 2
                collect(chunk[:mid])
                collect(chunk[mid:])
                return
        successes.append(document)
        for category_id in chunk:
            if category_id in pending:
                pending.remove(category_id)
        for entry in document.get("categories", []):
            merge_mapping(output_path, [{"categories": [entry]}])
            print(
                f"  added mapping: {entry['category_id']} ({entry.get('name')})",
                file=sys.stderr,
            )
        print(
            f"  mapped {len(chunk)} (total {sum(len(d['categories']) for d in successes)})",
            file=sys.stderr,
        )

    batch_size = max(1, args.batch_size)
    while pending:
        chunk = pending[:batch_size]
        print(f"Processing {len(chunk)} categories...", file=sys.stderr)
        collect(chunk)

    if successes:
        merge_mapping(output_path, successes)
        print(
            f"Wrote {sum(len(d['categories']) for d in successes)} mappings to {output_path}",
            file=sys.stderr,
        )

    if failures:
        print(
            f"Could not discover {len(failures)} categories: {sorted(failures)}",
            file=sys.stderr,
        )
        return 1
    print("All leaf categories mapped successfully.", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover Digikala API mappings for every leaf category."
    )
    parser.add_argument(
        "--category-manifest",
        default="core/management/data/categories.json",
        help="Path to the canonical category manifest.",
    )
    parser.add_argument(
        "--output",
        default="core/management/data/digikala_category_mappings.json",
        help="Destination approved mapping file.",
    )
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--chromium-path", help="Explicit Chromium executable path.")
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
