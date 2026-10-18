from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.api.permissions import (
    CatalogModelPermissions,
    CustomActionPermission,
)
from domains.catalog.api.vendor_product_review_serializers import (
    VendorProductApplySerializer,
    VendorProductDecideSerializer,
    VendorProductNoteSerializer,
    VendorProductReviewDetailSerializer,
    VendorProductReviewListSerializer,
)
from domains.catalog.models import VendorProduct, VendorProductStatus
from domains.catalog.services.vendor_product_submission_service import (
    VendorProductSubmissionService,
    vendor_product_submission_service,
)


def _get_submission(id):
    submission = VendorProduct.objects.select_related(
        "status", "product", "vendor"
    ).filter(pk=id).first()
    if submission is None:
        raise NotFound(_("Submission not found."))
    return submission


class VendorProductReviewList(APIView):
    """The confirmation queue. `?status=` is a review code, `queue` (default)
    for everything waiting, or `all` for the full history."""

    model = VendorProduct
    permission_classes = [CatalogModelPermissions]

    def get(self, request):
        submissions = VendorProduct.objects.select_related(
            "status", "product", "brand", "vendor"
        ).prefetch_related(
            "categories",
            "product_files__file",
            "vendor__business_profiles",
        ).order_by("-updated_at", "-id")

        status_filter = request.query_params.get("status", "queue")
        if status_filter == "queue":
            submissions = submissions.filter(
                status__name__in=[
                    code.value for code in VendorProductStatus.PENDING_CODES
                ]
            )
        elif status_filter != "all":
            submissions = submissions.filter(status__name=status_filter)

        vendor_id = request.query_params.get("vendor_id")
        if vendor_id:
            submissions = submissions.filter(vendor_id=vendor_id)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(submissions, request, view=self)
        serializer = VendorProductReviewListSerializer(page, many=True)
        return api_response(
            True, "", paginator.get_paginated_response(serializer.data).data
        )


class VendorProductReviewDetail(APIView):
    model = VendorProduct
    permission_classes = [CatalogModelPermissions]

    def get(self, request, id):
        return api_response(
            True, "", VendorProductReviewDetailSerializer(_get_submission(id)).data
        )


class VendorProductReviewConfirm(APIView):
    """First approval: the draft becomes a live catalog product."""

    permission_classes = [CustomActionPermission]
    required_permission = "catalog.change_vendorproduct"

    def post(self, request, id):
        submission = _get_submission(id)
        serializer = VendorProductNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = vendor_product_submission_service.confirm(
                submission,
                admin=request.user,
                response=serializer.validated_data.get("response"),
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Product added to the catalog."),
            VendorProductReviewDetailSerializer(submission).data,
        )


class VendorProductReviewApply(APIView):
    """Revision approval: only the fields the admin ticks are copied."""

    permission_classes = [CustomActionPermission]
    required_permission = "catalog.change_vendorproduct"

    def post(self, request, id):
        submission = _get_submission(id)
        serializer = VendorProductApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = vendor_product_submission_service.apply(
                submission,
                admin=request.user,
                fields=serializer.validated_data["fields"],
                response=serializer.validated_data.get("response"),
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Changes applied to the catalog."),
            VendorProductReviewDetailSerializer(submission).data,
        )


class VendorProductReviewDecide(APIView):
    """Send a submission back to the vendor without touching the catalog."""

    permission_classes = [CustomActionPermission]
    required_permission = "catalog.change_vendorproduct"

    def post(self, request, id):
        submission = _get_submission(id)
        serializer = VendorProductDecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = vendor_product_submission_service.decide(
                submission,
                code=serializer.validated_data["status"],
                response=serializer.validated_data.get("response"),
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Submission returned to the vendor."),
            VendorProductReviewDetailSerializer(submission).data,
        )
