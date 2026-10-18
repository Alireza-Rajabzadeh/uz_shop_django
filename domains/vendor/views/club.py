"""The seller's own view of the vendor club.

A seller can see their membership, their point summary, and their own point
ledger and nothing else. There is deliberately no write path here: balances
move only through ``domains.vendors_club.services.PointsService``, and every
read is scoped to the authenticated vendor rather than checked afterwards.
"""

from django.db.models import (
    BigIntegerField,
    Case,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.vendors_club.models import VendorClubPointTransaction
from domains.vendors_club.services import PointsService

from ..auth import VendorJWTAuthentication
from ..serializers.club import (
    VendorClubMembershipSerializer,
    VendorClubSummarySerializer,
    VendorClubTransactionQuerySerializer,
    VendorClubTransactionSerializer,
)


def _signed_points(direction):
    """A row's points carrying the sign one direction table gives its type.

    ``points`` is stored positive and the transaction type carries the sign, so
    the direction tables in ``PointsService`` are read here rather than
    re-declared in SQL. That keeps the running balance and the reconciliation
    reading the same rule.
    """
    return Case(
        *[
            When(transaction_type=code, then=F("points") * multiplier)
            for code, multiplier in direction.items()
        ],
        default=Value(0),
        output_field=BigIntegerField(),
    )


def _running_total(direction):
    """Correlated running total of a direction's points up to each row.

    Filters narrow which rows the list returns, and SQL applies ``WHERE``
    before a window function, so a ``Window`` would only sum the filtered
    subset and report a balance that never existed. This subquery walks the
    membership's full ledger up to and including the row instead, so the
    balance it reports is the real one under any filter.
    """
    rows = VendorClubPointTransaction.objects.filter(
        membership=OuterRef("membership_id"),
    ).filter(
        Q(created_at__lt=OuterRef("created_at"))
        | Q(created_at=OuterRef("created_at"), id__lte=OuterRef("id"))
    )
    return Subquery(
        rows.order_by()
        .values("membership")
        .annotate(total=Sum(_signed_points(direction)))
        .values("total")[:1],
        output_field=BigIntegerField(),
    )


class VendorClubMembershipView(APIView):
    """The caller's club membership and current point balances.

    `get_membership` creates the membership on first read and rebuilds the
    cached balances from the ledger when they are past the sync interval, so
    the numbers returned are always the reconciled ones.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = PointsService.get_membership(request.user)
        return api_response(data=VendorClubMembershipSerializer(membership).data)


class VendorClubSummaryView(APIView):
    """The caller's balances plus aggregates over their own ledger.

    Balances are reconciled through `get_membership`, so they agree with the
    membership endpoint. The per-type totals count the *magnitude* stored on
    each row; the transaction type carries the sign.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = PointsService.get_membership(request.user)
        ledger = membership.transactions
        totals = {
            row["transaction_type"]: row["total"]
            for row in ledger.values("transaction_type").annotate(
                total=Sum("points")
            )
        }
        payload = {
            "lifetime_points": membership.lifetime_points,
            "available_points": membership.available_points,
            "transaction_count": ledger.count(),
            "totals_by_type": {
                code: totals.get(code, 0)
                for code, _label in VendorClubPointTransaction.TransactionType.choices
            },
            "last_activity_at": ledger.order_by("-created_at", "-id")
            .values_list("created_at", flat=True)
            .first(),
            "member_since": membership.created_at,
            "last_synced_at": membership.last_synced_at,
        }
        return api_response(data=VendorClubSummarySerializer(payload).data)


class VendorClubTransactionListView(APIView):
    """The caller's own point ledger, newest movement first.

    Filtered by the authenticated vendor, so another seller's movements can
    never appear. Optional filters narrow the type, activity, and date range,
    and each row carries the balance it produced. Read-only: the ledger is
    appended to only by the service.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = VendorClubTransactionQuerySerializer(
            data=request.query_params.dict()
        )
        query.is_valid(raise_exception=True)
        filters = query.validated_data

        transactions = (
            VendorClubPointTransaction.objects.filter(
                membership__vendor=request.user
            )
            .select_related("activity")
            .annotate(
                lifetime_points_after=_running_total(
                    PointsService.LIFETIME_DIRECTION
                ),
                available_points_after=_running_total(
                    PointsService.AVAILABLE_DIRECTION
                ),
            )
        )

        if filters.get("transaction_type"):
            transactions = transactions.filter(
                transaction_type=filters["transaction_type"]
            )
        if filters.get("activity"):
            transactions = transactions.filter(
                activity__code=filters["activity"]
            )
        if filters.get("created_from"):
            transactions = transactions.filter(
                created_at__date__gte=filters["created_from"]
            )
        if filters.get("created_to"):
            transactions = transactions.filter(
                created_at__date__lte=filters["created_to"]
            )

        ordering = filters.get("ordering") or "-created_at"
        tiebreaker = "id" if not ordering.startswith("-") else "-id"
        transactions = transactions.order_by(ordering, tiebreaker)

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(transactions, request, view=self)
        serializer = VendorClubTransactionSerializer(page, many=True)
        return api_response(
            data=paginator.get_paginated_response(serializer.data).data
        )
