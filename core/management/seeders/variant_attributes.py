import json
from pathlib import Path

from django.db.models.functions import Lower, Trim

from core.management.seeders.base import BaseSeeder
from domains.catalog.models import (
    Category,
    CategoryVariantAttribute,
    VariantAttribute,
    VariantOption,
)


class VariantAttributeSeeder(BaseSeeder):
    MANIFEST_PATH = Path(__file__).resolve().parents[1] / "data" / "variant_attributes.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if manifest.get("schema_version") != 1:
            raise ValueError("Unsupported variant attribute manifest schema version.")

        attributes = manifest.get("attributes")
        if not isinstance(attributes, list):
            raise ValueError("Variant attribute manifest must contain an attributes list.")

        attribute_names = set()
        option_codes = set()
        for record in attributes:
            if not isinstance(record, dict):
                raise ValueError("Every attribute manifest entry must be an object.")
            name = record.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise ValueError(f"Invalid attribute name: {name!r}")
            normalized_name = " ".join(name.split()).casefold()
            if normalized_name in attribute_names:
                raise ValueError(f"Duplicate attribute name: {name!r}")
            attribute_names.add(normalized_name)

            options = record.get("options")
            if not isinstance(options, list):
                raise ValueError(f"Attribute {name!r} must contain an options list.")
            for option in options:
                if not isinstance(option, dict):
                    raise ValueError("Every option manifest entry must be an object.")
                sku_code = option.get("sku_code")
                if not isinstance(sku_code, str) or not sku_code.strip() or len(sku_code) > 16:
                    raise ValueError(f"Invalid option SKU code: {sku_code!r}")
                if sku_code.casefold() in option_codes:
                    raise ValueError(f"Duplicate option SKU code: {sku_code!r}")
                option_codes.add(sku_code.casefold())

            categories = record.get("categories", [])
            if not isinstance(categories, list):
                raise ValueError(f"Attribute {name!r} categories must be a list.")

        category_ids = {
            category_id
            for record in attributes
            for category_id in record.get("categories", [])
        }
        existing = set(
            Category.objects.filter(id__in=category_ids).values_list("id", flat=True)
        )
        missing = category_ids - existing
        if missing:
            raise ValueError(
                f"Attribute categories reference categories that do not exist: {sorted(missing)}"
            )
        return attributes

    def run(self):
        attributes = self._load_manifest()
        imported_count = 0
        for record in attributes:
            attribute_name = " ".join(record["name"].split())
            attribute = VariantAttribute.objects.annotate(
                normalized_name=Lower(Trim("name"))
            ).filter(normalized_name=attribute_name.casefold()).first()
            if attribute is None:
                attribute = VariantAttribute.objects.create(name=attribute_name)
            elif attribute.name != attribute_name:
                attribute.name = attribute_name
                attribute.save(update_fields=["name"])

            for option in record["options"]:
                option_name = option["name"]
                fa_name = option.get("fa_name")
                info = option.get("info", "")
                sku_code = option["sku_code"]
                existing = VariantOption.objects.filter(
                    sku_code__iexact=sku_code
                ).first()
                if existing is None:
                    VariantOption.objects.create(
                        attribute=attribute,
                        name=option_name,
                        fa_name=fa_name,
                        info=info,
                        sku_code=sku_code,
                    )
                else:
                    existing.attribute = attribute
                    existing.name = option_name
                    existing.fa_name = fa_name
                    existing.info = info
                    existing.sku_code = sku_code
                    existing.save(
                        update_fields=[
                            "attribute",
                            "name",
                            "fa_name",
                            "info",
                            "sku_code",
                        ]
                    )

            desired_categories = set(record.get("categories", []))
            existing_assignments = {
                assignment.category_id
                for assignment in attribute.category_assignments.all()
            }
            for category_id in desired_categories - existing_assignments:
                CategoryVariantAttribute.objects.create(
                    category_id=category_id, attribute=attribute
                )
            imported_count += 1
        return imported_count
