"""The admin panel's vendor club API.

Staff with the club permissions manage the earning activities, inspect every
membership and its balances, read the whole ledger across vendors, rebuild a
membership from its ledger, and record a hand-entered movement. Only the
movement write reaches the ledger, and it goes through `PointsService` like
every other writer.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions, CustomActionPermission
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)
from .serializers import (
    VendorClubActivityCreateSerializer,
    VendorClubActivityQuerySerializer,
    VendorClubActivitySerializer,
    VendorClubActivityUpdateSerializer,
    VendorClubMembershipDetailSerializer,
    VendorClubMembershipQuerySerializer,
    VendorClubMembershipSerializer,
    VendorClubOverviewSerializer,
    VendorClubTransactionCreateSerializer,
    VendorClubTransactionQuerySerializer,
    VendorClubTransactionSerializer,
)
from .services import AdminClubService, LedgerError, PointsService


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


def _paginated(queryset, request, view, serializer_class):
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    data = serializer_class(page, many=True).data
    return api_response(True, "", paginator.get_paginated_response(data).data)


def _activity(activity_id):
    activity = AdminClubService.get_activity(activity_id)
    if activity is None:
        raise NotFound(_("Activity not found."))
    return activity


def _membership(membership_id):
    membership = AdminClubService.get_membership(membership_id)
    if membership is None:
        raise NotFound(_("Membership not found."))
    return membership


# --- activities -------------------------------------------------------


class AdminVendorClubActivityList(AdminAPIView):
    model = VendorClubActivity

    def get(self, request):
        query = VendorClubActivityQuerySerializer(
            data=request.query_params.dict()
        )
        query.is_valid(raise_exception=True)
        activities = AdminClubService.list_activities(**query.validated_data)
        return _paginated(
            activities, request, self, VendorClubActivitySerializer
        )

    def post(self, request):
        serializer = VendorClubActivityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity = AdminClubService.create_activity(**serializer.validated_data)
        return api_response(
            True,
            _("Activity created."),
            VendorClubActivitySerializer(activity).data,
            status_code=201,
        )


class AdminVendorClubActivityDetail(AdminAPIView):
    model = VendorClubActivity

    def get(self, request, activity_id):
        activity = _activity(activity_id)
        return api_response(
            True, "", VendorClubActivitySerializer(activity).data
        )

    def patch(self, request, activity_id):
        activity = _activity(activity_id)
        serializer = VendorClubActivityUpdateSerializer(
            activity, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        activity = AdminClubService.update_activity(
            activity, **serializer.validated_data
        )
        return api_response(
            True, _("Activity updated."), VendorClubActivitySerializer(activity).data
        )


# --- memberships ------------------------------------------------------


class AdminVendorClubMembershipList(AdminAPIView):
    model = VendorClubMembership

    def get(self, request):
        query = VendorClubMembershipQuerySerializer(
            data=request.query_params.dict()
        )
        query.is_valid(raise_exception=True)
        memberships = AdminClubService.list_memberships(**query.validated_data)
        return _paginated(
            memberships, request, self, VendorClubMembershipSerializer
        )


class AdminVendorClubMembershipDetail(AdminAPIView):
    model = VendorClubMembership

    def get(self, request, membership_id):
        membership = _membership(membership_id)
        return api_response(
            True, "", VendorClubMembershipDetailSerializer(membership).data
        )


class AdminVendorClubMembershipResync(APIView):
    """Rebuild a membership's cached balances from its ledger.

    Its own view class because it is a POST action rather than a create: it
    needs `change` on the membership, not `add`, and `AdminModelPermissions`
    would map POST to `add` if it were a create route.
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [CustomActionPermission]
    required_permissions = ("vendors_club.change_vendorclubmembership",)

    def post(self, request, membership_id):
        membership = _membership(membership_id)
        result = PointsService.sync_points(membership)
        data = VendorClubMembershipSerializer(result.membership).data
        data["repaired"] = result.repaired
        return api_response(True, _("Balances rebuilt from the ledger."), data)


# --- ledger -----------------------------------------------------------


class AdminVendorClubTransactionList(AdminAPIView):
    model = VendorClubPointTransaction

    def get(self, request):
        query = VendorClubTransactionQuerySerializer(
            data=request.query_params.dict()
        )
        query.is_valid(raise_exception=True)
        transactions = AdminClubService.list_transactions(**query.validated_data)
        return _paginated(
            transactions, request, self, VendorClubTransactionSerializer
        )

    def post(self, request):
        serializer = VendorClubTransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry = PointsService.record_transaction(**serializer.validated_data)
        except LedgerError as exc:
            raise ValidationError({"detail": exc.message}) from exc
        return api_response(
            True,
            _("Point movement recorded."),
            VendorClubTransactionSerializer(entry).data,
            status_code=201,
        )


class AdminVendorClubTransactionDetail(AdminAPIView):
    model = VendorClubPointTransaction

    def get(self, request, transaction_id):
        entry = AdminClubService.get_transaction(transaction_id)
        if entry is None:
            raise NotFound(_("Transaction not found."))
        return api_response(
            True, "", VendorClubTransactionSerializer(entry).data
        )


# --- overview ---------------------------------------------------------


class AdminVendorClubOverview(AdminAPIView):
    model = VendorClubMembership

    def get(self, request):
        return api_response(
            True, "", VendorClubOverviewSerializer(AdminClubService.overview()).data
        )
