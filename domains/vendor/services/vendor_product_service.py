from django.db.models import Q, Value, BooleanField, Case, When
from rapidfuzz import fuzz
from rest_framework.exceptions import PermissionDenied

from domains.catalog.models import Category, Product, ProductStatus
from domains.catalog.services import ProductService


product_service = ProductService()


class VendorProductService:

    VENDOR_EDITABLE_STATUSES = frozenset({
        "wait_for_admin_confirmation",
        "admin_rejected",
    })

    @staticmethod
    def can_vendor_edit(product, vendor):
        if product.created_by_vendor_id != vendor.pk:
            return False
        if product.creator_model != "vendor.vendor":
            return False
        status_name = product.status.name.lower() if product.status_id else ""
        return status_name in VendorProductService.VENDOR_EDITABLE_STATUSES

    @staticmethod
    def get_editable_annotation(vendor):
        return Case(
            When(
                Q(created_by_vendor=vendor)
                & Q(creator_model="vendor.vendor")
                & Q(status__name__iexact="wait_for_admin_confirmation"),
                then=Value(True),
            ),
            When(
                Q(created_by_vendor=vendor)
                & Q(creator_model="vendor.vendor")
                & Q(status__name__iexact="admin_rejected"),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )

    @staticmethod
    def get_created_by_me_annotation(vendor):
        return Case(
            When(
                Q(created_by_vendor=vendor)
                & Q(creator_model="vendor.vendor"),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )

    # ─────────────────────── Variants ───────────────────────

    VARIANT_PENDING_STATUS = "wait_for_admin_confirmation"

    # The two levels of the variant rules. Level one is the product: variants
    # are only added or managed while the product itself is activated. Level
    # two is the variant: its creator may still shape a row waiting for review,
    # an active row is open, and nothing else is.
    PRODUCT_VARIANT_STATUS = "active"
    VARIANT_ACTIVE_STATUS = "active"
    VARIANT_DETAIL_STATUSES = frozenset({VARIANT_PENDING_STATUS, VARIANT_ACTIVE_STATUS})
    VARIANT_COMMERCIAL_STATUSES = frozenset({VARIANT_ACTIVE_STATUS})

    @staticmethod
    def is_variant_awaiting_confirmation(variant):
        """True while the variant is still queued for admin review.

        Status, not `confirmed_by`, is the gate: existing rows predate the
        confirmation column and are already live.
        """
        return bool(variant.status_id) and (
            variant.status.name.lower()
            == VendorProductService.VARIANT_PENDING_STATUS
        )

    @staticmethod
    def can_vendor_edit_variant(variant, vendor):
        """Whether this vendor may reshape the variant (its selections).

        Only the creator may edit, and only while the variant still waits for
        admin confirmation. Once confirmed the definition is locked; the vendor
        then manages price and stock instead.
        """
        if variant.created_by_vendor_id != vendor.pk:
            return False
        if variant.creator_model != "vendor.vendor":
            return False
        return VendorProductService.is_variant_awaiting_confirmation(variant)

    @staticmethod
    def can_vendor_read_variant(variant, vendor):
        """Whether `vendor` may see this variant at all.

        Only a pending row is hidden. Until an admin confirms it the draft
        belongs to whoever created it, so another vendor must not see it — or
        reach it through any id — while it waits. Everything else is shared
        catalog and stays readable by every vendor selling the product.
        """
        if not VendorProductService.is_variant_awaiting_confirmation(variant):
            return True
        return (
            variant.created_by_vendor_id == vendor.pk
            and variant.creator_model == "vendor.vendor"
        )

    @staticmethod
    def visible_variants(queryset, vendor):
        """Restrict a variant queryset to the rows `vendor` may read.

        Queryset form of `can_vendor_read_variant` for list endpoints; the two
        express one rule and must stay in step.
        """
        pending = Q(status__name__iexact=VendorProductService.VARIANT_PENDING_STATUS)
        mine = Q(created_by_vendor=vendor, creator_model="vendor.vendor")
        return queryset.filter(~pending | mine)

    @staticmethod
    def _status_name(row):
        """Lower-cased status name of a product or variant, `""` when unset."""
        return row.status.name.lower() if row.status_id else ""

    @staticmethod
    def assert_product_can_manage_variants(product):
        """Level one: variants may only be added or managed on an active product.

        Drafts, products waiting for review, rejected and disabled products are
        all closed for variant writes, so this runs before any payload is read.
        """
        if (
            VendorProductService._status_name(product)
            != VendorProductService.PRODUCT_VARIANT_STATUS
        ):
            raise PermissionDenied(
                "This product must be active before its variants can be added or managed."
            )

    @staticmethod
    def can_manage_variant_detail(variant):
        """Level two for the definition: its own pending draft, or active."""
        return (
            VendorProductService._status_name(variant)
            in VendorProductService.VARIANT_DETAIL_STATUSES
        )

    @staticmethod
    def assert_variant_detail_manageable(variant):
        """Gate for `PATCH /vendor/variants/<id>`.

        Both levels are checked before the payload: the product has to be
        active, and the variant has to be either its creator's pending draft or
        an active row. `inactive` and half-pending rows are closed.
        """
        VendorProductService.assert_product_can_manage_variants(variant.product)
        if not VendorProductService.can_manage_variant_detail(variant):
            raise PermissionDenied(
                "This variant cannot be edited while it is not active "
                "or waiting for admin confirmation."
            )

    @staticmethod
    def assert_variant_manageable(variant):
        """Block commercial writes until an admin confirms the variant.

        Pricing, stock, supplies and marketplace listing all sit downstream of
        a reviewed, active definition, so they wait with it. The read endpoints
        stay open: the vendor still needs to see their pending variant.
        """
        VendorProductService.assert_product_can_manage_variants(variant.product)
        status_name = VendorProductService._status_name(variant)
        if status_name == VendorProductService.VARIANT_PENDING_STATUS:
            raise PermissionDenied(
                "This variant is waiting for admin confirmation."
            )
        if status_name not in VendorProductService.VARIANT_COMMERCIAL_STATUSES:
            raise PermissionDenied(
                "This variant must be active before it can be managed."
            )

    @staticmethod
    def find_similar_products(name, category_ids=None, limit=10, threshold=65):
        from domains.files.services.file_service import FileService
        from django.db.models import Prefetch
        from domains.catalog.models import ProductFile

        normalized = " ".join(name.split()).casefold()
        queryset = Product.objects.select_related("brand", "status").prefetch_related(
            "categories",
            Prefetch(
                "product_files",
                queryset=ProductFile.objects.filter(role="thumbnail", file__file_type="image").select_related("file"),
                to_attr="prefetched_thumbnails",
            ),
        )

        if category_ids:
            queryset = queryset.filter(categories__id__in=category_ids).distinct()

        matches = []
        for product in queryset:
            product_name = product.name.casefold()
            score = round(fuzz.WRatio(normalized, product_name))
            exact = " ".join(product.name.split()).casefold() == normalized
            if exact or score >= threshold:
                brand_data = None
                if product.brand_id:
                    brand_data = {
                        "id": product.brand_id,
                        "name": product.brand.name,
                        "fa_name": product.brand.fa_name,
                    }
                
                thumbnail_url = None
                thumbnails = getattr(product, "prefetched_thumbnails", [])
                if thumbnails:
                    try:
                        thumbnail_url = FileService().url(thumbnails[0].file)
                    except Exception:
                        thumbnail_url = None
                
                matches.append({
                    "id": product.id,
                    "name": product.name,
                    "brand": brand_data,
                    "categories": [
                        {"id": c.id, "name": c.name, "fa_name": c.fa_name}
                        for c in product.categories.all()
                    ],
                    "status_name": product.status.name if product.status_id else None,
                    "similarity": score,
                    "exact": exact,
                    "thumbnail_url": thumbnail_url,
                })

        matches.sort(key=lambda m: (not m["exact"], -m["similarity"], m["name"].casefold()))
        return matches[:limit]

    @staticmethod
    def create_vendor_product(*, vendor, name, category_ids, brand=None, description=None, details=()):
        from domains.catalog.models import ProductStatus as PS

        product = product_service.create_complete_product(
            name=name,
            category_ids=category_ids,
            brand=brand,
            description=description,
            details=details,
        )

        wait_status = PS.objects.get(name__iexact="wait_for_admin_confirmation")
        product.status = wait_status
        product.created_by_vendor = vendor
        product.creator_model = "vendor.vendor"
        product.save(update_fields=["status", "created_by_vendor", "creator_model"])

        return product

    @staticmethod
    def create_vendor_variant(vendor, product, **data):
        """Create a variant owned by the vendor and queued for review.

        Ownership plus the pending status are what make the variant editable
        by its creator and everything else blocked, so both are stamped here
        rather than left for the view to remember.
        """
        from domains.catalog.models import ProductVariantStatus

        wait_status = ProductVariantStatus.objects.get(
            name__iexact=VendorProductService.VARIANT_PENDING_STATUS
        )
        variant = product_service.add_variant_to_product(
            product, status_id=wait_status.pk, **data
        )
        variant.created_by_vendor = vendor
        variant.creator_model = "vendor.vendor"
        variant.save(update_fields=["created_by_vendor", "creator_model"])
        return variant

    @staticmethod
    def update_vendor_product(product, vendor, **data):
        if not VendorProductService.can_vendor_edit(product, vendor):
            raise PermissionDenied("You do not have permission to edit this product.")

        if "category_ids" not in data:
            data["category_ids"] = list(
                product.categories.order_by("pk")
            )
        else:
            raw_ids = data.pop("category_ids")
            cat_ids = [
                c.pk if hasattr(c, "pk") else c for c in raw_ids
            ]
            data["category_ids"] = list(
                Category.objects.filter(pk__in=cat_ids).order_by("pk")
            )

        product = product_service.update_complete_product(product, **data)

        wait_status = ProductStatus.objects.get(name__iexact="wait_for_admin_confirmation")
        product.status = wait_status
        product.save(update_fields=["status"])

        return product

    @staticmethod
    def can_manage_variants(product):
        """Level one for creation: only an activated product takes variants."""
        return (
            VendorProductService._status_name(product)
            == VendorProductService.PRODUCT_VARIANT_STATUS
        )
