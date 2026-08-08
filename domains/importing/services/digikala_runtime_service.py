import fcntl
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from django.conf import settings

from domains.importing.integrations.digikala.contracts import (
    ApprovedCategory,
    load_approved_mapping,
    validate_mappings,
)
from domains.importing.integrations.digikala.filesystem import read_json, write_json_atomic
from domains.importing.integrations.digikala.pipeline import validate_listing_document


class DigikalaRuntimeService:
    class Error(Exception):
        pass

    JOB_TERMINAL = {
        "completed",
        "completed_with_errors",
        "failed",
        "cancelled",
        "queue_failed",
    }

    def __init__(self, root=None, mapping_path=None):
        self.root = Path(root or settings.DIGIKALA_RUNTIME_ROOT).resolve()
        self.mapping_path = Path(
            mapping_path or settings.DIGIKALA_CATEGORY_MAPPING_PATH
        ).resolve()
        self.listings_dir = self.root / "listings"
        self.jobs_dir = self.root / "jobs"
        self.locks_dir = self.root / "locks"
        for directory in (self.listings_dir, self.jobs_dir, self.locks_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _uuid(value, field="id"):
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError) as exc:
            raise DigikalaRuntimeService.Error(f"Invalid {field}.") from exc

    def _job_dir(self, job_id):
        return self.jobs_dir / self._uuid(job_id, "job ID")

    def _manifest_path(self, job_id):
        return self._job_dir(job_id) / "manifest.json"

    def listing_path(self, listing_id):
        return self.listings_dir / f"{self._uuid(listing_id, 'listing ID')}.json"

    @contextmanager
    def lock(self, name):
        path = self.locks_dir / f"{name}.lock"
        with path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def approved_categories(self):
        try:
            return load_approved_mapping(self.mapping_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise self.Error(f"Approved category mapping is invalid: {exc}") from exc

    def _mapping_document(self):
        try:
            data = read_json(self.mapping_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise self.Error(f"Approved category mapping is invalid: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
            raise self.Error("Approved category mapping must contain a categories list.")
        return data

    def _write_mapping_categories(self, categories):
        document = self._mapping_document()
        document["schema"] = "uzshop.digikala.category-mappings/v1"
        document["categories"] = [entry.as_dict() for entry in categories]
        payload = json.dumps(document, ensure_ascii=False, indent=2)
        try:
            existing = self.mapping_path.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if existing is not None and (existing == payload or existing == payload + "\n"):
            return
        import os
        import tempfile as _tempfile

        descriptor, temporary_name = _tempfile.mkstemp(
            prefix=f".{self.mapping_path.name}.",
            suffix=".tmp",
            dir=self.mapping_path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.mapping_path)
        finally:
            temporary.unlink(missing_ok=True)

    def list_mappings(self):
        return [
            category.as_dict()
            for category in sorted(
                self.approved_categories(), key=lambda item: item.category_id
            )
        ]

    def get_mapping(self, category_id):
        category_id = int(category_id)
        for category in self.approved_categories():
            if category.category_id == category_id:
                return category.as_dict()
        raise self.Error("Mapping was not found.")

    @staticmethod
    def _auto_api_url(digikala_category_id):
        return (
            f"https://api.digikala.com/discovery/api/v2/categories/"
            f"{int(digikala_category_id)}/products?columns_per_page=3&page=1"
        )

    def create_mapping(self, *, category_id, name, digikala_category_id, api_url=None):
        try:
            entry = ApprovedCategory.from_dict(
                {
                    "category_id": category_id,
                    "name": name,
                    "digikala_category_id": digikala_category_id,
                    "api_url": api_url or self._auto_api_url(digikala_category_id),
                }
            )
        except (TypeError, ValueError) as exc:
            raise self.Error(str(exc)) from exc
        with self.lock("mapping"):
            current = self.approved_categories()
            if any(item.category_id == entry.category_id for item in current):
                raise self.Error("A mapping for this category already exists.")
            if any(
                item.digikala_category_id == entry.digikala_category_id
                for item in current
            ):
                raise self.Error(
                    "This Digikala category is already mapped to another category."
                )
            self._write_mapping_categories([*current, entry])
        return entry.as_dict()

    def update_mapping(
        self,
        category_id,
        *,
        name=None,
        digikala_category_id=None,
        api_url=None,
    ):
        category_id = int(category_id)
        with self.lock("mapping"):
            current = self.approved_categories()
            target_index = next(
                (
                    index
                    for index, item in enumerate(current)
                    if item.category_id == category_id
                ),
                None,
            )
            if target_index is None:
                raise self.Error("Mapping was not found.")
            target = current[target_index]
            if (
                digikala_category_id is not None
                and digikala_category_id != target.digikala_category_id
                and api_url is None
            ):
                api_url = self._auto_api_url(digikala_category_id)
            updated = {
                "category_id": target.category_id,
                "name": name if name is not None else target.name,
                "digikala_category_id": (
                    digikala_category_id
                    if digikala_category_id is not None
                    else target.digikala_category_id
                ),
                "api_url": api_url if api_url is not None else target.api_url,
            }
            try:
                entry = ApprovedCategory.from_dict(updated)
            except (TypeError, ValueError) as exc:
                raise self.Error(str(exc)) from exc
            if any(
                item.digikala_category_id == entry.digikala_category_id
                and item.category_id != entry.category_id
                for item in current
            ):
                raise self.Error(
                    "This Digikala category is already mapped to another category."
                )
            next_categories = list(current)
            next_categories[target_index] = entry
            self._write_mapping_categories(next_categories)
        return entry.as_dict()

    def delete_mapping(self, category_id):
        category_id = int(category_id)
        with self.lock("mapping"):
            current = self.approved_categories()
            remaining = [
                item for item in current if item.category_id != category_id
            ]
            if len(remaining) == len(current):
                raise self.Error("Mapping was not found.")
            if not remaining:
                raise self.Error("At least one approved category is required.")
            self._write_mapping_categories(remaining)

    def selected_categories(self, category_ids):
        requested = {int(category_id) for category_id in category_ids}
        mappings = {
            category.category_id: category for category in self.approved_categories()
        }
        missing = requested - set(mappings)
        if missing:
            raise self.Error(f"Categories are not approved: {sorted(missing)}")
        return [mappings[category_id] for category_id in sorted(requested)]

    def create_job(self, kind, request, created_by=None):
        job_id = str(uuid4())
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True)
        write_json_atomic(
            job_dir / "request.json",
            {
                "schema": f"uzshop.digikala.{kind}-request/v1",
                "job_id": job_id,
                "created_at": self.now(),
                "created_by": created_by,
                **request,
            },
        )
        manifest = {
            "schema": "uzshop.digikala.job/v1",
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "phase": "queued",
            "created_at": self.now(),
            "started_at": None,
            "finished_at": None,
            "heartbeat_at": None,
            "cancel_requested": False,
            "listing_id": request.get("listing_id"),
            "total_products": 0,
            "processed_products": 0,
            "imported_products": 0,
            "updated_products": 0,
            "failed_products": 0,
            "skipped_products": 0,
            "warnings": 0,
            "progress": 0,
            "current_product_id": None,
            "error": None,
            "results": {},
        }
        write_json_atomic(self._manifest_path(job_id), manifest)
        return manifest

    def get_request(self, job_id):
        path = self._job_dir(job_id) / "request.json"
        if not path.is_file():
            raise self.Error("Job request was not found.")
        return read_json(path)

    def get_job(self, job_id):
        path = self._manifest_path(job_id)
        if not path.is_file():
            raise self.Error("Job was not found.")
        return read_json(path)

    def update_job(self, job_id, **changes):
        with self.lock(f"job-{self._uuid(job_id)}"):
            manifest = self.get_job(job_id)
            manifest.update(changes)
            manifest["heartbeat_at"] = self.now()
            if manifest.get("total_products"):
                manifest["progress"] = round(
                    manifest.get("processed_products", 0)
                    * 100
                    / manifest["total_products"]
                )
            write_json_atomic(self._manifest_path(job_id), manifest, overwrite=True)
        return manifest

    def update_result(self, job_id, product_id, result):
        with self.lock(f"job-{self._uuid(job_id)}"):
            manifest = self.get_job(job_id)
            results = manifest.setdefault("results", {})
            results[str(product_id)] = result
            write_json_atomic(self._manifest_path(job_id), manifest, overwrite=True)
        return manifest

    def append_event(self, job_id, event):
        path = self._job_dir(job_id) / "events.jsonl"
        record = {"at": self.now(), **event}
        with self.lock(f"events-{self._uuid(job_id)}"):
            with path.open("a", encoding="utf-8") as event_file:
                event_file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                event_file.write("\n")

    def request_cancel(self, job_id):
        manifest = self.get_job(job_id)
        if manifest["status"] not in self.JOB_TERMINAL:
            manifest = self.update_job(
                job_id, cancel_requested=True, status="cancel_requested"
            )
        return manifest

    def is_cancel_requested(self, job_id):
        return bool(self.get_job(job_id).get("cancel_requested"))

    def list_jobs(self):
        jobs = []
        for path in self.jobs_dir.glob("*/manifest.json"):
            try:
                jobs.append(read_json(path))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)

    def save_listing(self, source_path):
        document = validate_listing_document(read_json(source_path))
        destination = self.listing_path(document["listing_id"])
        if destination.exists():
            existing = validate_listing_document(read_json(destination))
            if existing["sha256"] != document["sha256"]:
                raise self.Error("Listing ID already exists with different content.")
            return existing
        Path(source_path).replace(destination)
        return document

    def get_listing(self, listing_id):
        path = self.listing_path(listing_id)
        if not path.is_file():
            raise self.Error("Listing was not found.")
        try:
            return validate_listing_document(read_json(path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise self.Error(f"Listing is invalid: {exc}") from exc

    def list_listings(self):
        listings = []
        for path in self.listings_dir.glob("*.json"):
            try:
                document = validate_listing_document(read_json(path))
                stat = path.stat()
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            listings.append(
                {
                    "id": document["listing_id"],
                    "created_at": document["generated_at"],
                    "status": "complete",
                    "category_count": document["summary"]["category_count"],
                    "product_count": document["summary"]["unique_product_count"],
                    "size": stat.st_size,
                    "sha256": document["sha256"],
                }
            )
        return sorted(listings, key=lambda item: item["created_at"], reverse=True)

    def selected_product_ids(self, listing, selection):
        available = {int(product["product_id"]) for product in listing["products"]}
        if selection.get("mode") == "all":
            return sorted(available)
        try:
            selected = {int(product_id) for product_id in selection["product_ids"]}
        except (KeyError, TypeError, ValueError) as exc:
            raise self.Error("Selected product IDs are invalid.") from exc
        missing = selected - available
        if missing:
            raise self.Error(f"Products are not in the listing: {sorted(missing)}")
        return sorted(selected)

    def failed_product_ids(self, job_id):
        manifest = self.get_job(job_id)
        return sorted(
            int(product_id)
            for product_id, result in manifest.get("results", {}).items()
            if result.get("status") == "failed"
        )
