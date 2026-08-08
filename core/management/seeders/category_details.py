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
    MANIFEST_PATH = Path(__file__).resolve().parents[1] / "data" / "category_details.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if manifest.get("schema_version") != 1:
            raise ValueError("Unsupported category detail manifest schema version.")

        details = manifest.get("details")
        relations = manifest.get("relations")
        if not isinstance(details, list) or not isinstance(relations, list):
            raise ValueError(
                "Category detail manifest must contain details and relations lists."
            )

        valid_types = {choice for choice, _ in CATEGORY_DETAIL_TYPE_CHOICES}
        names = set()
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
            detail = CategoryDetail.objects.annotate(
                normalized_name=Lower(Trim("name"))
            ).filter(normalized_name=name.casefold()).first()
            if detail is None:
                detail = CategoryDetail.objects.create(name=name, type=record["type"])
            updates = {}
            if detail.name != name:
                updates["name"] = name
            if detail.type != record["type"]:
                updates["type"] = record["type"]
            if detail.required != record.get("required", False):
                updates["required"] = bool(record.get("required", False))
            if detail.options != record.get("options", ""):
                updates["options"] = record.get("options", "")
            if detail.filterable != record.get("filterable", True):
                updates["filterable"] = bool(record.get("filterable", True))
            if updates:
                detail.save(update_fields=list(updates))
            detail_by_name[name.casefold()] = detail

        desired = set()
        for record in relations:
            category = Category.objects.get(pk=record["category_id"])
            detail = detail_by_name[" ".join(record["detail"].split()).casefold()]
            CategoryDetailRelation.objects.update_or_create(
                category=category,
                detail=detail,
                defaults={"value": record.get("value", "")},
            )

        return len(details)
