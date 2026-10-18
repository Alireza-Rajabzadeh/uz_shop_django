from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.api.serializers import (
    ProductFileReorderSerializer,
    ProductFileUpdateSerializer,
    ProductFileWriteSerializer,
)
from domains.catalog.models import VendorProduct
from domains.catalog.services import ProductFileService, VendorProductFileService
from domains.catalog.services.vendor_product_submission_service import (
    VendorProductSubmissionService,
    vendor_product_submission_service,
)
from domains.packages.permissions import RequiresShopProducts
from domains.vendor.auth import VendorJWTAuthentication
from domains.vendor.serializers.product_submissions import (
    VendorProductSubmissionCreateSerializer,
    VendorProductSubmissionDetailSerializer,
    VendorProductSubmissionListSerializer,
    VendorProductSubmissionUpdateSerializer,
    VendorSubmissionFileSerializer,
)
from domains.vendor.views.products import (
    _get_business_category_ids,
    _get_vendor_product,
)


vendor_product_file_service = VendorProductFileService()


def _category_ids(request):
    """The categories this vendor's business is approved to trade in."""
    _, category_ids = _get_business_category_ids(request.user)
    return category_ids or None


def _get_submission(submission_id, vendor):
    submission = VendorProduct.objects.select_related(
        "status", "product", "brand"
    ).filter(pk=submission_id, vendor=vendor).first()
    if submission is None:
        # Another vendor's submission reports as missing, not forbidden.
        raise NotFound("Submission not found.")
    return submission


def _assert_categories_in_scope(category_ids, allowed):
    """A vendor may only file products under its own approved categories."""
    outside = sorted(set(category_ids) - set(allowed))
    if outside:
        raise ValidationError(
            {"category_ids": [_("You can only use categories your business is approved for.")]}
        )


def _detail(submission):
    return VendorProductSubmissionDetailSerializer(submission).data


class VendorProductSubmissionListView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def get(self, request):
        submissions = VendorProduct.objects.filter(
            vendor=request.user
        ).select_related("status", "product", "brand").prefetch_related(
            "categories", "product_files__file"
        ).order_by("-updated_at", "-id")

        status_code = request.query_params.get("status")
        if status_code:
            submissions = submissions.filter(status__name=status_code)
        product_id = request.query_params.get("product_id")
        if product_id:
            submissions = submissions.filter(product_id=product_id)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(submissions, request, view=self)
        serializer = VendorProductSubmissionListSerializer(page, many=True)
        return api_response(
            data=paginator.get_paginated_response(serializer.data).data
        )

    def post(self, request):
        category_ids = _category_ids(request)
        if category_ids is None:
            return api_response(False, "Business profile not found.", status_code=404)

        serializer = VendorProductSubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("product_id") is not None:
            product = _get_vendor_product(data["product_id"], category_ids)
            submission = vendor_product_submission_service.create_or_get_baseline(
                vendor=request.user, product=product
            )
            return api_response(
                True, "Draft ready.", _detail(submission), status_code=201
            )

        _assert_categories_in_scope(data.get("category_ids") or [], category_ids)
        try:
            submission = vendor_product_submission_service.create_submission(
                vendor=request.user,
                **{key: value for key, value in data.items() if key != "product_id"},
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True, "Draft created.", _detail(submission), status_code=201
        )


class VendorProductSubmissionDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def get(self, request, id):
        return api_response(data=_detail(_get_submission(id, request.user)))

    def patch(self, request, id):
        category_ids = _category_ids(request)
        if category_ids is None:
            return api_response(False, "Business profile not found.", status_code=404)

        submission = _get_submission(id, request.user)
        serializer = VendorProductSubmissionUpdateSerializer(
            data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        if "category_ids" in serializer.validated_data:
            _assert_categories_in_scope(
                serializer.validated_data["category_ids"], category_ids
            )

        try:
            submission = vendor_product_submission_service.update_submission(
                submission, vendor=request.user, **serializer.validated_data
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(data=_detail(submission))

    def delete(self, request, id):
        submission = _get_submission(id, request.user)
        submission = vendor_product_submission_service.discard(
            submission, vendor=request.user
        )
        if submission is None:
            return api_response(True, "Draft discarded.", None)
        return api_response(True, "Changes withdrawn.", _detail(submission))


class VendorProductSubmissionSubmitView(APIView):
    """Hand a finished draft to the admin. Frozen from here until returned."""

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def post(self, request, id):
        submission = _get_submission(id, request.user)
        try:
            submission = vendor_product_submission_service.submit(
                submission, vendor=request.user
            )
        except VendorProductSubmissionService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "Sent for review.", _detail(submission))


# ─────────────────────── Draft media ───────────────────────


class VendorProductSubmissionFileListCreateView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def get(self, request, submission_id):
        submission = _get_submission(submission_id, request.user)
        relations = vendor_product_file_service.list_for_product(submission)
        return api_response(
            data=VendorSubmissionFileSerializer(relations, many=True).data
        )

    def post(self, request, submission_id):
        submission = _get_submission(submission_id, request.user)
        vendor_product_submission_service.require_editable(submission, request.user)
        serializer = ProductFileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = vendor_product_file_service.attach(
                submission, **serializer.validated_data
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "File attached to draft.",
            VendorSubmissionFileSerializer(relation).data,
            status_code=201,
        )


class VendorProductSubmissionFileDetailView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def _get_relation(self, request, submission_id, relation_id):
        submission = _get_submission(submission_id, request.user)
        relation = vendor_product_file_service.get_for_product(
            submission, relation_id
        )
        if relation is None:
            raise NotFound("Draft file not found.")
        return submission, relation

    def patch(self, request, submission_id, relation_id):
        submission, relation = self._get_relation(
            request, submission_id, relation_id
        )
        vendor_product_submission_service.require_editable(submission, request.user)
        serializer = ProductFileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation = vendor_product_file_service.update(
                relation, **serializer.validated_data
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Draft file updated.",
            VendorSubmissionFileSerializer(relation).data,
        )

    def delete(self, request, submission_id, relation_id):
        submission, relation = self._get_relation(
            request, submission_id, relation_id
        )
        vendor_product_submission_service.require_editable(submission, request.user)
        vendor_product_file_service.delete(relation)
        return api_response(True, "File detached from draft.", None)


class VendorProductSubmissionFileReorderView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated, RequiresShopProducts]

    def patch(self, request, submission_id):
        submission = _get_submission(submission_id, request.user)
        vendor_product_submission_service.require_editable(submission, request.user)
        serializer = ProductFileReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relations = vendor_product_file_service.reorder(
                submission, serializer.validated_data["files"]
            )
        except ProductFileService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            "Draft files reordered.",
            VendorSubmissionFileSerializer(relations, many=True).data,
        )
