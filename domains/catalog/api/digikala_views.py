from math import ceil

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.api.digikala_serializers import (
    DigikalaImportCreateSerializer,
    DigikalaListingCreateSerializer,
)
from domains.catalog.api.permissions import (
    AllRequiredPermissions,
    CustomActionPermission,
    MethodPermission,
)
from domains.catalog.services.digikala_runtime_service import DigikalaRuntimeService
from domains.catalog.tasks import collect_digikala_listing, import_digikala_products
from domains.users.auth import AdminJWTAuthentication


def _paginate(request, items, default_size=20, maximum=100):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(
            maximum, max(1, int(request.query_params.get("page_size", default_size)))
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid pagination values.") from exc
    count = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    pages = ceil(count / page_size) if count else 1
    return {
        "count": count,
        "next": page + 1 if page < pages else None,
        "previous": page - 1 if page > 1 and page <= pages + 1 else None,
        "results": items[start:end],
    }


class DigikalaAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, CustomActionPermission]
    required_permission = "catalog.view_product"

    @staticmethod
    def runtime():
        return DigikalaRuntimeService()

    def handle_runtime_error(self, exc):
        raise ValidationError(str(exc)) from exc


class DigikalaListingOptions(DigikalaAPIView):
    def get(self, request):
        try:
            categories = [
                {
                    "id": category.category_id,
                    "name": category.name,
                    "digikala_category_id": category.digikala_category_id,
                }
                for category in self.runtime().approved_categories()
            ]
        except DigikalaRuntimeService.Error as exc:
            self.handle_runtime_error(exc)
        return api_response(
            True,
            "",
            {
                "categories": categories,
                "limits": {
                    "max_categories": 5,
                    "max_products_per_category": 20,
                    "max_unique_products": 100,
                    "min_delay_seconds": 0.5,
                    "max_delay_seconds": 10,
                },
                "currency": "IRR",
            },
        )


class DigikalaListingListCreate(DigikalaAPIView):
    permission_classes = [IsAuthenticated, MethodPermission]
    method_permissions = {
        "GET": "catalog.view_product",
        "POST": "catalog.add_product",
    }

    def get(self, request):
        return api_response(True, "", _paginate(request, self.runtime().list_listings()))

    def post(self, request):
        serializer = DigikalaListingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        runtime = self.runtime()
        try:
            runtime.selected_categories(serializer.validated_data["category_ids"])
            job = runtime.create_job(
                "listing",
                serializer.validated_data,
                created_by=request.user.id,
            )
            collect_digikala_listing.apply_async(
                args=[job["id"]], queue="digikala"
            )
        except DigikalaRuntimeService.Error as exc:
            self.handle_runtime_error(exc)
        except Exception as exc:
            if "job" in locals():
                runtime.update_job(
                    job["id"], status="queue_failed", error=str(exc)
                )
            raise ValidationError("Listing job could not be queued.") from exc
        return api_response(
            True,
            "Listing job queued.",
            {"job_id": job["id"], "status": job["status"]},
            status_code=202,
        )


class DigikalaListingProducts(DigikalaAPIView):
    def get(self, request, listing_id):
        runtime = self.runtime()
        try:
            listing = runtime.get_listing(listing_id)
        except DigikalaRuntimeService.Error as exc:
            raise NotFound(str(exc)) from exc
        products = listing["products"]
        search = request.query_params.get("search", "").strip().casefold()
        category_id = request.query_params.get("category_id")
        if search:
            products = [
                product
                for product in products
                if search
                in " ".join(
                    str(value or "")
                    for value in (
                        product.get("product_id"),
                        product.get("title_fa"),
                        product.get("title_en"),
                        product.get("brand", {}).get("title_fa"),
                        product.get("brand", {}).get("title_en"),
                    )
                ).casefold()
            ]
        if category_id:
            try:
                selected_category = int(category_id)
            except ValueError as exc:
                raise ValidationError("Invalid category ID.") from exc
            products = [
                product
                for product in products
                if selected_category in product.get("category_ids", [])
            ]
        data = _paginate(request, products, default_size=20)
        data["listing_sha256"] = listing["sha256"]
        return api_response(True, "", data)


class DigikalaImportCreate(DigikalaAPIView):
    permission_classes = [IsAuthenticated, AllRequiredPermissions]
    required_permissions = (
        "catalog.view_product",
        "catalog.add_product",
        "catalog.change_product",
        "catalog.add_detail_to_product",
        "catalog.add_variant_to_product",
    )

    def post(self, request):
        serializer = DigikalaImportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        runtime = self.runtime()
        try:
            listing = runtime.get_listing(data["listing_id"])
            if listing["sha256"] != data["listing_sha256"]:
                raise DigikalaRuntimeService.Error("Listing checksum changed.")
            selected = runtime.selected_product_ids(listing, data["selection"])
            if len(selected) > 100:
                raise DigikalaRuntimeService.Error(
                    "At most 100 unique products may be imported."
                )
            request_data = {
                "listing_id": str(data["listing_id"]),
                "listing_sha256": data["listing_sha256"],
                "selection": data["selection"],
                "options": data["options"],
            }
            job = runtime.create_job(
                "import", request_data, created_by=request.user.id
            )
            import_digikala_products.apply_async(
                args=[job["id"]], queue="digikala"
            )
        except DigikalaRuntimeService.Error as exc:
            self.handle_runtime_error(exc)
        except Exception as exc:
            if "job" in locals():
                runtime.update_job(
                    job["id"], status="queue_failed", error=str(exc)
                )
            raise ValidationError("Import job could not be queued.") from exc
        return api_response(
            True,
            "Import job queued.",
            {"job_id": job["id"], "status": job["status"]},
            status_code=202,
        )


class DigikalaJobList(DigikalaAPIView):
    def get(self, request):
        return api_response(True, "", _paginate(request, self.runtime().list_jobs()))


class DigikalaJobDetail(DigikalaAPIView):
    def get(self, request, job_id):
        try:
            job = self.runtime().get_job(job_id)
        except DigikalaRuntimeService.Error as exc:
            raise NotFound(str(exc)) from exc
        response = api_response(True, "", job)
        response["Cache-Control"] = "no-store"
        return response


class DigikalaJobCancel(DigikalaAPIView):
    permission_classes = [IsAuthenticated, MethodPermission]
    method_permissions = {"POST": "catalog.change_product"}

    def post(self, request, job_id):
        try:
            job = self.runtime().request_cancel(job_id)
        except DigikalaRuntimeService.Error as exc:
            raise NotFound(str(exc)) from exc
        return api_response(True, "Cancellation requested.", job)


class DigikalaJobRetryFailures(DigikalaAPIView):
    permission_classes = [IsAuthenticated, AllRequiredPermissions]
    required_permissions = DigikalaImportCreate.required_permissions

    def post(self, request, job_id):
        runtime = self.runtime()
        try:
            original = runtime.get_job(job_id)
            if original.get("kind") != "import":
                raise DigikalaRuntimeService.Error(
                    "Only import failures can be retried."
                )
            failed = runtime.failed_product_ids(job_id)
            if not failed:
                raise DigikalaRuntimeService.Error("The job has no failed products.")
            source_request = runtime.get_request(job_id)
            retry_request = {
                "listing_id": source_request["listing_id"],
                "listing_sha256": source_request["listing_sha256"],
                "selection": {"mode": "ids", "product_ids": failed},
                "options": source_request["options"],
                "retry_of": str(job_id),
            }
            job = runtime.create_job(
                "import", retry_request, created_by=request.user.id
            )
            import_digikala_products.apply_async(
                args=[job["id"]], queue="digikala"
            )
        except DigikalaRuntimeService.Error as exc:
            self.handle_runtime_error(exc)
        return api_response(
            True,
            "Failed products queued for retry.",
            {"job_id": job["id"], "status": job["status"]},
            status_code=202,
        )
