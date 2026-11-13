import json
from pathlib import Path

from django.db.models.functions import Lower, Trim

from core.management.seeders.base import BaseSeeder
from domains.catalog.models import Brand


class BrandSeeder(BaseSeeder):
    MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "brands.json"

    def __init__(self, manifest_path=None):
        self.manifest_path = Path(manifest_path) if manifest_path else self.MANIFEST_PATH

    def _load_manifest(self):
        with self.manifest_path.open(encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        if "schema_version" in manifest and manifest.get("schema_version") != 1:
            raise ValueError("Unsupported brand manifest schema version.")

        brands = manifest.get("brands")
        if not isinstance(brands, list):
            raise ValueError("Brand manifest must contain a brands list.")

        names = set()
        ids = set()
        for record in brands:
            if not isinstance(record, dict):
                raise ValueError("Every brand manifest entry must be an object.")
            name = record.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 150:
                raise ValueError(f"Invalid brand name: {name!r}")
            normalized_name = " ".join(name.split()).casefold()
            if normalized_name in names:
                raise ValueError(f"Duplicate brand name: {name!r}")
            names.add(normalized_name)

            brand_id = record.get("id")
            if brand_id is not None:
                if not isinstance(brand_id, int) or brand_id <= 0:
                    raise ValueError(f"Invalid brand ID: {brand_id!r}")
                if brand_id in ids:
                    raise ValueError(f"Duplicate brand ID: {brand_id}")
                ids.add(brand_id)

        return brands

    def run(self):
        brands = self._load_manifest()
        imported_count = 0
        for record in brands:
            name = " ".join(record["name"].split())
            fa_name = record.get("fa_name")
            brand_id = record.get("id")

            existing = (
                Brand.objects.annotate(normalized_name=Lower(Trim("name")))
                .filter(normalized_name=name.casefold())
                .first()
            )

            if brand_id is not None:
                if existing and existing.id != brand_id:
                    existing.name = f"__brand_legacy_{existing.id}__"
                    existing.save(update_fields=["name"])

                Brand.objects.update_or_create(
                    id=brand_id,
                    defaults={"name": name, "fa_name": fa_name},
                )
            else:
                if existing:
                    updates = []
                    if existing.name != name:
                        existing.name = name
                        updates.append("name")
                    if existing.fa_name != fa_name:
                        existing.fa_name = fa_name
                        updates.append("fa_name")
                    if updates:
                        existing.save(update_fields=updates)
                else:
                    Brand.objects.create(name=name, fa_name=fa_name)

            imported_count += 1

        self.sync_sequence(Brand)
        return imported_count
