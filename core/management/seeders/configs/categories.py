import json
from pathlib import Path

from django.db import transaction

from core.management.seeders.base import BaseSeeder
from domains.catalog.enums.CategoryStatusEnum import CategoryStatusEnum
from domains.catalog.models import Category, CategoryStatus


class CategorySeeder(BaseSeeder):
    MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "categories.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if "schema_version" in manifest and manifest.get("schema_version") != 1:
            raise ValueError("Unsupported category manifest schema version.")

        categories = manifest.get("categories")
        if not isinstance(categories, list):
            raise ValueError("Category manifest must contain a categories list.")

        ids = set()
        source_urls = set()

        def validate(records):
            sibling_names = set()
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Every category manifest entry must be an object.")

                category_id = record.get("id")
                name = record.get("name")
                source_url = record.get("source_url")
                children = record.get("children")
                if not isinstance(category_id, int) or category_id <= 0:
                    raise ValueError(f"Invalid imported category ID: {category_id!r}")
                if category_id in ids:
                    raise ValueError(f"Duplicate imported category ID: {category_id}")
                ids.add(category_id)

                if not isinstance(name, str) or not name.strip() or len(name) > 100:
                    raise ValueError(f"Invalid imported category name for ID {category_id}.")
                normalized_name = " ".join(name.split()).casefold()
                if normalized_name in sibling_names:
                    raise ValueError(f"Duplicate sibling category name: {name!r}")
                sibling_names.add(normalized_name)

                if not isinstance(source_url, str) or not source_url.startswith("/"):
                    raise ValueError(f"Invalid source URL for category ID {category_id}.")
                if source_url in source_urls:
                    raise ValueError(f"Duplicate category source URL: {source_url}")
                source_urls.add(source_url)

                if not isinstance(children, list):
                    raise ValueError(f"Category {category_id} must contain a children list.")
                validate(children)

        validate(categories)
        if manifest.get("category_count") is not None and manifest.get("category_count") != len(ids):
            raise ValueError("Category manifest count does not match its records.")
        return categories

    @transaction.atomic
    def run(self):
        categories = self._load_manifest()
        for status in CategoryStatusEnum:
            CategoryStatus.objects.update_or_create(
                id=status.value,
                defaults={"name": status.name.lower()},
            )

        manifest_ids = []
        all_manifest_names = set()

        def collect(records):
            for r in records:
                manifest_ids.append(r["id"])
                all_manifest_names.add(r["name"].strip().casefold())
                collect(r.get("children", []))

        collect(categories)

        # Free unique normalized names on existing categories to prevent constraint collision when shifting IDs
        for cat in Category.objects.select_for_update().filter(id__in=manifest_ids):
            cat.name = f"__category_seed_{cat.id}__"
            cat.save(update_fields=["name"])

        for cat in Category.objects.select_for_update().exclude(id__in=manifest_ids):
            if cat.name.strip().casefold() in all_manifest_names:
                cat.name = f"__category_seed_{cat.id}__"
                cat.save(update_fields=["name"])

        imported_count = 0

        def seed(records, parent=None):
            nonlocal imported_count
            for record in records:
                category, _ = Category.objects.update_or_create(
                    id=record["id"],
                    defaults={
                        "name": record["name"],
                        "fa_name": record.get("fa_name") or record["name"],
                        "status_id": CategoryStatusEnum.ACTIVE.value,
                        "parent": parent,
                    },
                )
                imported_count += 1
                seed(record.get("children", []), category)

        seed(categories)
        self.sync_sequences(CategoryStatus, Category)
        return imported_count
