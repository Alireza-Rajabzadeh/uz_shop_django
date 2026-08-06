import json
from pathlib import Path

from django.core.management.color import no_style
from django.db import connection, transaction

from core.management.seeders.base import BaseSeeder
from domains.catalog.enums.CategoryStatusEnum import CategoryStatusEnum
from domains.catalog.models import Category, CategoryStatus


class CategorySeeder(BaseSeeder):
    MANIFEST_PATH = Path(__file__).resolve().parents[1] / "data" / "categories.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if manifest.get("schema_version") != 1:
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
                if not isinstance(category_id, int) or category_id < 1001:
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
        if manifest.get("category_count") != len(ids):
            raise ValueError("Category manifest count does not match its records.")
        if sorted(ids) != list(range(1001, 1001 + len(ids))):
            raise ValueError("Imported category IDs must be contiguous from 1001.")
        return categories

    @transaction.atomic
    def run(self):
        categories = self._load_manifest()
        for status in CategoryStatusEnum:
            CategoryStatus.objects.update_or_create(
                id=status.value,
                defaults={"name": status.name.lower()},
            )

        imported_count = 0

        def seed(records, parent=None):
            nonlocal imported_count
            for record in records:
                category, _ = Category.objects.update_or_create(
                    id=record["id"],
                    defaults={
                        "name": record["name"],
                        "fa_name": record["name"],
                        "status_id": CategoryStatusEnum.ACTIVE.value,
                        "parent": parent,
                    },
                )
                imported_count += 1
                seed(record["children"], category)

        seed(categories)
        statements = connection.ops.sequence_reset_sql(no_style(), [Category])
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        return imported_count
