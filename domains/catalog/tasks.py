from celery import shared_task

from domains.catalog.integrations.digikala import ListingOptions, collect_listings
from domains.catalog.integrations.digikala.client import DigikalaClient
from domains.catalog.integrations.digikala.contracts import detail_url
from domains.catalog.integrations.digikala.detail import normalize_detail
from domains.catalog.integrations.digikala.filesystem import write_json_atomic
from domains.catalog.services.digikala_import_service import DigikalaImportService
from domains.catalog.services.digikala_runtime_service import DigikalaRuntimeService


def _finish_cancelled(runtime, job_id):
    return runtime.update_job(
        job_id,
        status="cancelled",
        phase="cancelled",
        finished_at=runtime.now(),
        current_product_id=None,
    )


@shared_task(name="catalog.digikala.collect_listing")
def collect_digikala_listing(job_id):
    runtime = DigikalaRuntimeService()
    request = runtime.get_request(job_id)
    manifest = runtime.get_job(job_id)
    if manifest["status"] in runtime.JOB_TERMINAL:
        return manifest
    runtime.update_job(
        job_id,
        status="running",
        phase="listings",
        started_at=manifest.get("started_at") or runtime.now(),
    )
    temporary = runtime._job_dir(job_id) / "listing.json"

    def progress(event):
        runtime.append_event(job_id, event)
        runtime.update_job(job_id, phase="listings")

    try:
        with runtime.lock("listing"):
            if runtime.is_cancel_requested(job_id):
                return _finish_cancelled(runtime, job_id)
            temporary.unlink(missing_ok=True)
            mappings = runtime.selected_categories(request["category_ids"])
            options = ListingOptions(
                products_per_category=request["products_per_category"],
                timeout=request["timeout_seconds"],
                retries=request["retries"],
                delay=request["delay_seconds"],
                include_ads=request["include_ads"],
            )
            document = collect_listings(
                mappings,
                options,
                temporary,
                progress=progress,
                cancel=lambda: runtime.is_cancel_requested(job_id),
            )
            runtime.save_listing(temporary)
        return runtime.update_job(
            job_id,
            status="completed",
            phase="completed",
            listing_id=document["listing_id"],
            total_products=document["summary"]["unique_product_count"],
            processed_products=document["summary"]["unique_product_count"],
            progress=100,
            finished_at=runtime.now(),
        )
    except Exception as exc:
        if runtime.is_cancel_requested(job_id):
            return _finish_cancelled(runtime, job_id)
        runtime.append_event(job_id, {"phase": "listings", "error": str(exc)})
        runtime.update_job(
            job_id,
            status="failed",
            phase="failed",
            error=str(exc),
            finished_at=runtime.now(),
        )
        raise


@shared_task(name="catalog.digikala.import_products")
def import_digikala_products(job_id):
    runtime = DigikalaRuntimeService()
    request = runtime.get_request(job_id)
    manifest = runtime.get_job(job_id)
    if manifest["status"] in runtime.JOB_TERMINAL:
        return manifest
    listing = runtime.get_listing(request["listing_id"])
    if listing["sha256"] != request["listing_sha256"]:
        runtime.update_job(
            job_id,
            status="failed",
            phase="failed",
            error="Listing checksum changed.",
            finished_at=runtime.now(),
        )
        return
    product_ids = runtime.selected_product_ids(listing, request["selection"])
    product_map = {
        int(product["product_id"]): product for product in listing["products"]
    }
    runtime.update_job(
        job_id,
        status="running",
        phase="details",
        started_at=manifest.get("started_at") or runtime.now(),
        total_products=len(product_ids),
    )
    client = DigikalaClient(
        timeout=request.get("timeout_seconds", 30),
        retries=request.get("retries", 3),
        delay=request.get("delay_seconds", 1.0),
    )
    importer = DigikalaImportService()
    details_dir = runtime._job_dir(job_id) / "details"
    details_dir.mkdir(parents=True, exist_ok=True)

    try:
        with runtime.lock("import"):
            for product_id in product_ids:
                if runtime.is_cancel_requested(job_id):
                    return _finish_cancelled(runtime, job_id)
                current = runtime.get_job(job_id)
                previous = current.get("results", {}).get(str(product_id))
                if previous and previous.get("status") in {"created", "updated"}:
                    continue
                runtime.update_job(
                    job_id,
                    phase="details",
                    current_product_id=product_id,
                )
                try:
                    raw = client.get_detail(
                        detail_url(product_id), expected_product_id=product_id
                    )
                    write_json_atomic(
                        details_dir / f"{product_id}.raw.json", raw, overwrite=True
                    )
                    detail = normalize_detail(raw, product_id)
                    listing_product = product_map[product_id]
                    if not detail.get("brand") or not any(
                        detail["brand"].get(key)
                        for key in ("title_fa", "title_en", "code")
                    ):
                        detail["brand"] = listing_product.get("brand")
                    detail["listing_id"] = listing["listing_id"]
                    detail["category_ids"] = listing_product["category_ids"]
                    write_json_atomic(
                        details_dir / f"{product_id}.json", detail, overwrite=True
                    )
                    runtime.update_job(job_id, phase="importing")
                    result = importer.import_product(
                        detail, listing_product["category_ids"]
                    )
                    result["finished_at"] = runtime.now()
                    runtime.update_result(job_id, product_id, result)
                    current = runtime.get_job(job_id)
                    changes = {
                        "processed_products": current["processed_products"] + 1,
                        "current_product_id": product_id,
                        "warnings": current["warnings"]
                        + len(result.get("warnings", [])),
                    }
                    counter = (
                        "imported_products"
                        if result["status"] == "created"
                        else "updated_products"
                    )
                    changes[counter] = current[counter] + 1
                    runtime.update_job(job_id, **changes)
                    runtime.append_event(
                        job_id,
                        {
                            "phase": "importing",
                            "product_id": product_id,
                            "status": result["status"],
                        },
                    )
                except Exception as exc:
                    failure = {
                        "status": "failed",
                        "error": str(exc),
                        "finished_at": runtime.now(),
                    }
                    runtime.update_result(job_id, product_id, failure)
                    current = runtime.get_job(job_id)
                    runtime.update_job(
                        job_id,
                        processed_products=current["processed_products"] + 1,
                        failed_products=current["failed_products"] + 1,
                    )
                    runtime.append_event(
                        job_id,
                        {
                            "phase": "importing",
                            "product_id": product_id,
                            "status": "failed",
                            "error": str(exc),
                        },
                    )
                if product_id != product_ids[-1]:
                    client.sleep(request.get("delay_seconds", 1.0))
    except Exception as exc:
        if runtime.is_cancel_requested(job_id):
            return _finish_cancelled(runtime, job_id)
        runtime.update_job(
            job_id,
            status="failed",
            phase="failed",
            error=str(exc),
            finished_at=runtime.now(),
        )
        raise

    manifest = runtime.get_job(job_id)
    return runtime.update_job(
        job_id,
        status=(
            "completed_with_errors"
            if manifest["failed_products"]
            else "completed"
        ),
        phase="completed",
        progress=100,
        current_product_id=None,
        finished_at=runtime.now(),
    )
