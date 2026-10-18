from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied

from domains.catalog.models import (
    Category,
    CategoryDetail,
    Product,
    ProductDetails,
    ProductFile,
    ProductStatus,
    VendorProduct,
    VendorProductDetails,
    VendorProductFile,
    VendorProductStatus,
)
from domains.catalog.services.product_service import ProductService

# The catalog validator is the single statement of the rule "a detail value
# must belong to a detail the selected categories define, and every required
# one must be supplied". It is reused here verbatim so the rule cannot drift
# between the aggregate path and the submission path.
product_service = ProductService()


class VendorProductSubmissionService:
    """Owns a vendor product submission from draft to the catalog.

    One row carries two lanes, told apart by `product`:

    * `product` is null  -> first-time draft. `confirm` creates the catalog
      row and stamps `product`.
    * `product` is set   -> pending revision of a live product. `apply` copies
      the admin's selected fields onto that row.

    Review vocabulary is `VendorProductStatus`, deliberately separate from
    `ProductStatus`: the catalog describes what is live, this describes what
    is waiting for an admin.

    Invariant: status `confirmed` means the staging content equals the live
    content. Every path that leaves a row `confirmed` therefore has to copy
    what was selected and revert what was not.
    """

    APPLYABLE_FIELDS = frozenset({
        "name",
        "brand",
        "description",
        "json_description",
        "categories",
        "details",
        "media",
    })

    # A submission is with the admin only in `VendorProductStatus.PENDING_CODES`;
    # every other state is either being written by the vendor or has already
    # been decided, so it can be acted on.
    EDITABLE_CODES = frozenset({
        VendorProductStatus.Code.DRAFT,
        VendorProductStatus.Code.CONFIRMED,
        VendorProductStatus.Code.NEED_RECHECK,
        VendorProductStatus.Code.REJECT,
    })

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    # ── predicates ────────────────────────────────────────────────────

    @staticmethod
    def status_code(submission):
        return submission.status.name if submission.status_id else ""

    def is_pending(self, submission):
        return self.status_code(submission) in VendorProductStatus.PENDING_CODES

    def is_editable(self, submission):
        return self.status_code(submission) in self.EDITABLE_CODES

    @staticmethod
    def _require_owner(submission, vendor):
        if submission.vendor_id != getattr(vendor, "pk", None):
            raise PermissionDenied(
                "You do not have permission to edit this product."
            )

    def require_editable(self, submission, vendor):
        """Owner-and-queue gate every vendor-side write passes through.

        The service re-checks the same conditions after taking the row lock;
        this exists so a view can fail fast with a 403 instead of 500.
        """
        self._require_owner(submission, vendor)
        if not self.is_editable(submission):
            raise PermissionDenied("This product is awaiting admin review.")

    @staticmethod
    def _lock(submission):
        """Re-read the row under a lock so the queue state we check is current.

        Callers keep their own instance; mutating services refresh it before
        returning, so a caller that holds the object it passed in sees the
        write instead of a stale pre-write copy.
        """
        return (
            VendorProduct.objects.select_for_update(of=("self",))
            .select_related("status")
            .get(pk=submission.pk)
        )

    @staticmethod
    def _status(code):
        return VendorProductStatus.objects.get(name__iexact=code)

    @staticmethod
    def _queue_code(submission):
        """Which review state a submission enters when the vendor sends it."""
        if submission.product_id:
            return VendorProductStatus.Code.REQUEST_UPDATE
        return VendorProductStatus.Code.CONFIRMATION_AWAIT

    # ── input normalization ───────────────────────────────────────────

    @staticmethod
    def _normalize_categories(category_ids):
        category_ids = list(category_ids or [])
        if not category_ids:
            raise VendorProductSubmissionService.ValidationError(
                {"category_ids": [_("Select at least one category.")]}
            )
        if len(category_ids) != len(set(category_ids)):
            raise VendorProductSubmissionService.ValidationError(
                {"category_ids": [_("Each category can only be submitted once.")]}
            )
        categories = list(Category.objects.filter(id__in=category_ids))
        if len(categories) != len(set(category_ids)):
            raise VendorProductSubmissionService.ValidationError(
                {"category_ids": [_("One or more selected categories do not exist.")]}
            )
        return categories

    @staticmethod
    def _normalize_details(categories, details):
        """Resolve the panel's `{"detail_id", "value"}` payload to model refs.

        The API contract sends ids, the catalog validator reads instances.
        Resolving here also enforces that every id belongs to one of the
        selected categories, the same rule the admin aggregate endpoint
        applies to its own payload.
        """
        details = list(details or [])
        ids = []
        for item in details:
            if not isinstance(item, dict) or item.get("detail_id") is None:
                raise VendorProductSubmissionService.ValidationError(
                    {"details": [_("Each detail must have a 'detail_id' field.")]}
                )
            ids.append(item["detail_id"])
        if len(ids) != len(set(ids)):
            raise VendorProductSubmissionService.ValidationError(
                {"details": [_("Each product detail can only be submitted once.")]}
            )
        definitions = {
            detail.id: detail
            for detail in CategoryDetail.objects.filter(
                categorydetailrelation__category__in=categories
            ).distinct()
        }
        if set(ids) - set(definitions):
            raise VendorProductSubmissionService.ValidationError(
                {"details": [_("One or more details are not assigned to the selected category.")]}
            )
        return [
            {"detail": definitions[item["detail_id"]], "value": item.get("value", "") or ""}
            for item in details
        ]

    def _validate_detail_payload(self, categories, details):
        """Raise the catalog's detail errors under this service's type."""
        try:
            product_service._validate_complete_product_details(categories, details)
        except product_service.ValidationError as exc:
            raise VendorProductSubmissionService.ValidationError(exc.errors) from exc

    # ── row mirrors ───────────────────────────────────────────────────
    #
    # Both mirrors are exact: ids, options and ordering survive a copy so
    # that `confirmed` really does mean "the two sides are the same row".

    @staticmethod
    def _mirror_submission_details(submission, source_rows):
        VendorProductDetails.objects.filter(vendor_product=submission).delete()
        VendorProductDetails.objects.bulk_create([
            VendorProductDetails(
                vendor_product=submission,
                detail_id=row.detail_id,
                option_id=row.option_id,
                value=row.value,
                extra_value=row.extra_value,
            )
            for row in source_rows
        ])

    @staticmethod
    def _mirror_product_details(product, source_rows):
        ProductDetails.objects.filter(product=product).delete()
        ProductDetails.objects.bulk_create([
            ProductDetails(
                product=product,
                detail_id=row.detail_id,
                option_id=row.option_id,
                value=row.value,
                extra_value=row.extra_value,
            )
            for row in source_rows
        ])

    @staticmethod
    def _assert_media_usable(rows):
        """Refuse to publish media that went unavailable while queued."""
        for row in rows:
            if row.file.status.name != "available" or row.file.deleted_at is not None:
                raise VendorProductSubmissionService.ValidationError(
                    {"files": [_("One of the files is no longer available; ask the vendor to replace it.")]}
                )

    @staticmethod
    def _mirror_submission_files(submission, source_rows):
        VendorProductFile.objects.filter(vendor_product=submission).delete()
        VendorProductFile.objects.bulk_create([
            VendorProductFile(
                vendor_product=submission,
                file_id=row.file_id,
                role=row.role,
                position=row.position,
                is_primary=row.is_primary,
                alt_text=row.alt_text,
            )
            for row in source_rows
        ])

    @staticmethod
    def _mirror_product_files(product, source_rows):
        ProductFile.objects.filter(product=product).delete()
        ProductFile.objects.bulk_create([
            ProductFile(
                product=product,
                file_id=row.file_id,
                role=row.role,
                position=row.position,
                is_primary=row.is_primary,
                alt_text=row.alt_text,
            )
            for row in source_rows
        ])

    def _submission_files(self, submission):
        return list(
            submission.product_files.select_related(
                "file", "file__status"
            ).order_by("position", "id")
        )

    def _product_files(self, product):
        return list(
            product.product_files.select_related(
                "file", "file__status"
            ).order_by("position", "id")
        )

    def _write_submission_details(self, submission, items):
        """Persist a validated detail payload, dropping blank optionals.

        Mirrors `ProductService._replace_product_details`, which never
        carries `extra_value`, so the two sides stay comparable.
        """
        VendorProductDetails.objects.filter(vendor_product=submission).delete()
        VendorProductDetails.objects.bulk_create([
            VendorProductDetails(
                vendor_product=submission,
                detail=item["detail"],
                option=ProductService._get_detail_option(item["detail"], item["value"]),
                value=item["value"],
            )
            for item in items
            if item["value"] or item["detail"].required
        ])

    # ── vendor writes ─────────────────────────────────────────────────

    @transaction.atomic
    def create_submission(self, *, vendor, **data):
        """Open a first-time draft. `product_id` is the other lane."""
        name = (data.get("name") or "").strip()
        if not name:
            raise self.ValidationError({"name": [_("Enter a product name.")]})
        categories = self._normalize_categories(data.get("category_ids"))
        items = self._normalize_details(categories, data.get("details"))
        self._validate_detail_payload(categories, items)

        submission = VendorProduct(
            name=name,
            status=self._status(VendorProductStatus.Code.DRAFT),
            vendor=vendor,
            brand_id=data.get("brand_id"),
            description=data.get("description") or "",
            json_description=data.get("json_description") or {},
        )
        submission.save()
        submission.categories.set(categories)
        self._write_submission_details(submission, items)
        return submission

    @transaction.atomic
    def create_or_get_baseline(self, *, vendor, product):
        """Open (or return) the draft that stages edits to a live product.

        It starts as a `draft` — the vendor's own working copy, not yet
        anything the admin has been asked about.
        """
        existing = VendorProduct.objects.filter(product=product).select_related(
            "status"
        ).first()
        if existing is not None:
            if existing.vendor_id != vendor.pk:
                raise PermissionDenied(
                    "Another vendor is already editing this product."
                )
            return existing

        submission = VendorProduct(
            name=product.name,
            status=self._status(VendorProductStatus.Code.DRAFT),
            vendor=vendor,
            product=product,
            brand_id=product.brand_id,
            description=product.description or "",
            json_description=product.json_description or {},
        )
        submission.save()
        submission.categories.set(product.categories.all())
        self._mirror_submission_details(
            submission, product.details.select_related("detail")
        )
        self._mirror_submission_files(submission, self._product_files(product))
        return submission

    @transaction.atomic
    def update_submission(self, submission, *, vendor, **data):
        """Save edits. Any change re-enters the admin queue."""
        self._require_owner(submission, vendor)
        locked = self._lock(submission)
        # Re-checked once locked: the queue state is the guard, not the lookup.
        self._require_owner(locked, vendor)
        if not self.is_editable(locked):
            raise PermissionDenied("This product is awaiting admin review.")

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise self.ValidationError({"name": [_("Enter a product name.")]})
            locked.name = name
        if "description" in data:
            locked.description = data["description"] or ""
        if "json_description" in data:
            locked.json_description = data["json_description"] or {}
        if "brand_id" in data:
            locked.brand_id = data["brand_id"]
        locked.save()

        if "category_ids" in data:
            categories = self._normalize_categories(data["category_ids"])
            locked.categories.set(categories)
        else:
            categories = list(locked.categories.all())

        if "details" in data:
            items = self._normalize_details(categories, data["details"])
            self._validate_detail_payload(categories, items)
            self._write_submission_details(locked, items)

        # Editing never queues anything: the vendor sends explicitly. It does
        # have to drop a row out of `confirmed`, which promises the staged
        # content matches the catalog. A save that changed nothing keeps that
        # promise, so the row stays put.
        if (
            self.status_code(locked) == VendorProductStatus.Code.CONFIRMED
            and self.changed_fields(locked)
        ):
            locked.status = self._status(VendorProductStatus.Code.DRAFT)
        locked.save()
        submission.refresh_from_db()
        return locked

    @transaction.atomic
    def submit(self, submission, *, vendor):
        """Hand a finished submission to the admin and freeze it."""
        self._require_owner(submission, vendor)
        locked = self._lock(submission)
        self._require_owner(locked, vendor)
        if not self.is_editable(locked):
            raise PermissionDenied("This product is awaiting admin review.")

        code = self.status_code(locked)
        returned = code in (
            VendorProductStatus.Code.NEED_RECHECK,
            VendorProductStatus.Code.REJECT,
        )
        # Queuing a revision that differs from the catalog in no field would
        # put an empty row in front of an admin. The exception is a submission
        # just sent back for changes, where "I checked it, it is fine" is a
        # legitimate answer to the note.
        if (
            locked.product_id
            and not returned
            and not self.changed_fields(locked)
        ):
            raise self.ValidationError(
                {"status": [_("Nothing has changed to review.")]}
            )

        locked.status = self._status(self._queue_code(locked))
        locked.save()
        submission.refresh_from_db()
        return locked

    @transaction.atomic
    def discard(self, submission, *, vendor):
        """Throw away a draft, or withdraw a queued change set."""
        self._require_owner(submission, vendor)
        locked = self._lock(submission)
        self._require_owner(locked, vendor)
        if not self.is_editable(locked):
            raise PermissionDenied("This product is awaiting admin review.")

        if locked.product_id is None:
            locked.delete()
            return None

        live = locked.product
        locked.name = live.name
        locked.brand_id = live.brand_id
        locked.description = live.description
        locked.json_description = live.json_description
        locked.categories.set(live.categories.all())
        self._mirror_submission_details(
            locked, live.details.select_related("detail")
        )
        self._mirror_submission_files(locked, self._product_files(live))
        # Back in sync with the catalog, so the invariant holds again.
        locked.status = self._status(VendorProductStatus.Code.CONFIRMED)
        locked.admin_response = None
        locked.save()
        submission.refresh_from_db()
        return locked

    # ── admin writes ──────────────────────────────────────────────────

    @transaction.atomic
    def confirm(self, submission, *, admin, response=None):
        """First approval: the catalog row is created from the draft."""
        locked = self._lock(submission)
        if locked.product_id:
            raise self.ValidationError(
                {"status": [_("This submission already has a catalog product; apply it instead.")]}
            )
        if self.status_code(locked) != VendorProductStatus.Code.CONFIRMATION_AWAIT:
            raise self.ValidationError(
                {"status": [_("Nothing is awaiting confirmation.")]}
            )

        product = self._create_catalog_product(locked)
        locked.product = product
        locked.status = self._status(VendorProductStatus.Code.CONFIRMED)
        locked.confirmed_by = admin
        locked.confirmed_at = timezone.now()
        locked.admin_response = response or None
        locked.save()
        submission.refresh_from_db()
        return locked

    def _create_catalog_product(self, submission):
        categories = list(submission.categories.all())
        rows = list(submission.details.select_related("detail"))
        items = [{"detail": row.detail, "value": row.value} for row in rows]
        # Revalidate: a category may have gained a required detail, or lost
        # one of these, between submission and this confirmation.
        self._validate_detail_payload(categories, items)

        files = self._submission_files(submission)
        self._assert_media_usable(files)

        product = Product.objects.create(
            name=submission.name,
            status=ProductStatus.objects.get(name__iexact="active"),
            brand_id=submission.brand_id,
            description=submission.description or "",
            json_description=submission.json_description or {},
            # Match what the admin product list filters on for vendor rows.
            creator_model="vendor.vendor",
            created_by_vendor=submission.vendor,
        )
        product.categories.set(categories)
        self._mirror_product_details(product, rows)
        self._mirror_product_files(product, files)
        return product

    @transaction.atomic
    def apply(self, submission, *, admin, fields, response=None):
        """Copy the selected fields of a queued revision onto the live row."""
        locked = self._lock(submission)
        if not locked.product_id:
            raise self.ValidationError(
                {"status": [_("This submission has no catalog product yet; confirm it instead.")]}
            )
        if self.status_code(locked) != VendorProductStatus.Code.REQUEST_UPDATE:
            raise self.ValidationError(
                {"status": [_("Nothing is awaiting review.")]}
            )

        fields = set(fields or ())
        unknown = fields - self.APPLYABLE_FIELDS
        if unknown:
            raise self.ValidationError(
                {"fields": [_("Unknown field: %s") % ", ".join(sorted(unknown))]}
            )
        if not fields:
            raise self.ValidationError(
                {"fields": [_("Select at least one field to apply.")]}
            )

        live = Product.objects.select_for_update().get(pk=locked.product_id)
        submission_rows = list(locked.details.select_related("detail"))
        submission_files = self._submission_files(locked)

        categories_changed = "categories" in fields
        details_changed = "details" in fields
        if categories_changed or details_changed:
            categories = (
                list(locked.categories.all())
                if categories_changed
                else list(live.categories.all())
            )
            source_rows = submission_rows if details_changed else list(
                live.details.select_related("detail")
            )
            self._validate_detail_payload(
                categories,
                [{"detail": row.detail, "value": row.value} for row in source_rows],
            )

        update_fields = []
        if "name" in fields:
            live.name = locked.name
            update_fields.append("name")
        if "brand" in fields:
            live.brand_id = locked.brand_id
            update_fields.append("brand")
        if "description" in fields:
            live.description = locked.description or ""
            update_fields.append("description")
        if "json_description" in fields:
            live.json_description = locked.json_description or {}
            update_fields.append("json_description")
        if update_fields:
            live.save(update_fields=update_fields)

        if categories_changed:
            # TODO(admin-panel): nothing here checks the target categories
            # against the vendor's `BusinessProfile.categories`. An admin can
            # therefore approve a category the vendor itself could not have
            # chosen; the review UI has to surface that before apply.
            previous_ids = set(live.categories.values_list("id", flat=True))
            live.categories.set(locked.categories.all())
            if previous_ids != set(locked.categories.values_list("id", flat=True)):
                # SKU generation is owned by the catalog and is deliberately
                # unchanged here: a category change re-derives SKUs exactly as
                # it does on the admin aggregate path, and a collision is
                # surfaced back to the admin rather than swallowed.
                try:
                    with transaction.atomic():
                        product_service.regenerate_product_variant_skus(live)
                except IntegrityError as exc:
                    raise self.ValidationError(
                        {"category_ids": [_("Changing the category caused a generated SKU conflict.")]}
                    ) from exc

        if details_changed:
            self._mirror_product_details(live, submission_rows)
        if "media" in fields:
            self._assert_media_usable(submission_files)
            self._mirror_product_files(live, submission_files)

        # Revert everything that was not applied so `confirmed` still means
        # the two sides agree.
        if "name" not in fields:
            locked.name = live.name
        if "brand" not in fields:
            locked.brand_id = live.brand_id
        if "description" not in fields:
            locked.description = live.description
        if "json_description" not in fields:
            locked.json_description = live.json_description
        if not categories_changed:
            locked.categories.set(live.categories.all())
        if not details_changed:
            self._mirror_submission_details(
                locked, live.details.select_related("detail")
            )
        if "media" not in fields:
            self._mirror_submission_files(locked, self._product_files(live))

        locked.status = self._status(VendorProductStatus.Code.CONFIRMED)
        locked.confirmed_by = admin
        locked.confirmed_at = timezone.now()
        locked.admin_response = response or None
        locked.save()
        submission.refresh_from_db()
        return locked

    @transaction.atomic
    def decide(self, submission, *, code, response=None):
        """Send a queued submission back to the vendor without applying it."""
        try:
            code = VendorProductStatus.Code(code)
        except ValueError as exc:
            raise self.ValidationError(
                {"status": [_("Unknown status.")]}) from exc
        if code not in (
            VendorProductStatus.Code.NEED_RECHECK,
            VendorProductStatus.Code.REJECT,
        ):
            raise self.ValidationError(
                {"status": [_("Only 'need_recheck' and 'reject' can be decided here.")]}
            )

        locked = self._lock(submission)
        if not self.is_pending(locked):
            raise self.ValidationError(
                {"status": [_("This submission has already been decided.")]}
            )

        locked.status = self._status(code)
        locked.admin_response = response or None
        locked.save()
        submission.refresh_from_db()
        return locked

    # ── read side ─────────────────────────────────────────────────────

    @staticmethod
    def changed_fields(submission):
        """Which applyable fields currently differ from the live product."""
        if not submission.product_id:
            return set(VendorProductSubmissionService.APPLYABLE_FIELDS)

        live = submission.product
        changed = set()
        if submission.name != live.name:
            changed.add("name")
        if submission.brand_id != live.brand_id:
            changed.add("brand")
        if (submission.description or "") != (live.description or ""):
            changed.add("description")
        if (submission.json_description or {}) != (live.json_description or {}):
            changed.add("json_description")

        submission_category_ids = set(
            submission.categories.values_list("id", flat=True)
        )
        live_category_ids = set(live.categories.values_list("id", flat=True))
        if submission_category_ids != live_category_ids:
            changed.add("categories")

        def detail_signature(rows):
            return {
                (row.detail_id, row.option_id, row.value, row.extra_value)
                for row in rows
            }

        if detail_signature(submission.details.all()) != detail_signature(
            live.details.all()
        ):
            changed.add("details")

        def file_signature(rows):
            return [
                (row.file_id, row.role, row.position, row.is_primary, row.alt_text)
                for row in rows
            ]

        if file_signature(submission.product_files.all()) != file_signature(
            live.product_files.all()
        ):
            changed.add("media")
        return changed


vendor_product_submission_service = VendorProductSubmissionService()
