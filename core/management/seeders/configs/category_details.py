import json
from pathlib import Path

from django.db.models.functions import Lower, Trim

from core.constants import CATEGORY_DETAIL_TYPE_CHOICES
from core.management.seeders.base import BaseSeeder
from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
)


class CategoryDetailSeeder(BaseSeeder):
    MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "category_details.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if "schema_version" in manifest and manifest.get("schema_version") != 1:
            raise ValueError("Unsupported category detail manifest schema version.")

        details = manifest.get("details")
        relations = manifest.get("relations")
        if not isinstance(details, list) or not isinstance(relations, list):
            raise ValueError(
                "Category detail manifest must contain details and relations lists."
            )

        valid_types = {choice for choice, _ in CATEGORY_DETAIL_TYPE_CHOICES}
        names = set()
        ids = set()
        for record in details:
            if not isinstance(record, dict):
                raise ValueError("Every detail manifest entry must be an object.")
            name = record.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError(f"Invalid detail name: {name!r}")
            normalized_name = " ".join(name.split()).casefold()
            if normalized_name in names:
                raise ValueError(f"Duplicate detail name: {name!r}")
            names.add(normalized_name)
            if record.get("type") not in valid_types:
                raise ValueError(f"Invalid detail type for {name!r}.")

            detail_id = record.get("id")
            if detail_id is not None:
                if not isinstance(detail_id, int) or detail_id <= 0:
                    raise ValueError(f"Invalid detail ID: {detail_id!r}")
                if detail_id in ids:
                    raise ValueError(f"Duplicate detail ID: {detail_id}")
                ids.add(detail_id)

        for record in relations:
            if not isinstance(record, dict):
                raise ValueError("Every relation manifest entry must be an object.")
            detail_name = record.get("detail")
            if (
                not isinstance(detail_name, str)
                or " ".join(detail_name.split()).casefold() not in names
            ):
                raise ValueError(f"Relation references unknown detail {detail_name!r}.")
            if not isinstance(record.get("category_id"), int):
                raise ValueError("Relation category_id must be an integer.")

        category_ids = {record["category_id"] for record in relations}
        existing = set(Category.objects.filter(id__in=category_ids).values_list("id", flat=True))
        missing = category_ids - existing
        if missing:
            raise ValueError(
                f"Relations reference categories that do not exist: {sorted(missing)}"
            )
        return details, relations

    def run(self):
        details, relations = self._load_manifest()
        detail_by_name = {}
        for record in details:
            name = " ".join(record["name"].split())
            detail_id = record.get("id")
            detail_type = record.get("type", "text")
            required = bool(record.get("required", False))
            options = record.get("options", "")
            filterable = bool(record.get("filterable", True))

            existing = (
                CategoryDetail.objects.annotate(normalized_name=Lower(Trim("name")))
                .filter(normalized_name=name.casefold())
                .first()
            )

            defaults = {
                "name": name,
                "type": detail_type,
                "required": required,
                "options": options,
                "filterable": filterable,
            }

            if detail_id is not None:
                if existing and existing.id != detail_id:
                    existing.name = f"__category_detail_legacy_{existing.id}__"
                    existing.save(update_fields=["name"])

                detail, _ = CategoryDetail.objects.update_or_create(
                    id=detail_id,
                    defaults=defaults,
                )
            else:
                if existing:
                    updates = []
                    for field, value in defaults.items():
                        if getattr(existing, field) != value:
                            setattr(existing, field, value)
                            updates.append(field)
                    if updates:
                        existing.save(update_fields=updates)
                    detail = existing
                else:
                    detail = CategoryDetail.objects.create(**defaults)

            detail_by_name[name.casefold()] = detail

        for record in relations:
            category = Category.objects.get(pk=record["category_id"])
            detail = detail_by_name[" ".join(record["detail"].split()).casefold()]
            CategoryDetailRelation.objects.update_or_create(
                category=category,
                detail=detail,
                defaults={"value": record.get("value", "")},
            )

        self.sync_sequences(CategoryDetail, CategoryDetailRelation)
        return len(details)
