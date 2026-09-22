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

    VENDOR_CREATABLE_STATUSES = frozenset({
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
    def can_add_variant(product):
        status_name = product.status.name.lower() if product.status_id else ""
        return status_name not in VendorProductService.VENDOR_CREATABLE_STATUSES
