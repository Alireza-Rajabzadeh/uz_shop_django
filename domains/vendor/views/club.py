"""The seller's own view of the vendor club.

A seller can see their membership and their own point ledger and nothing else.
There is deliberately no write path here: balances move only through
``domains.vendors_club.services.PointsService``, and every read is scoped to
the authenticated vendor rather than checked afterwards.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.vendors_club.models import VendorClubPointTransaction
from domains.vendors_club.services import PointsService

from ..auth import VendorJWTAuthentication
from ..serializers.club import (
    VendorClubMembershipSerializer,
    VendorClubTransactionSerializer,
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


class VendorClubTransactionListView(APIView):
    """The caller's own point ledger, newest movement first.

    Filtered by the authenticated vendor, so another seller's movements can
    never appear. Read-only: the ledger is appended to only by the service.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = (
            VendorClubPointTransaction.objects.filter(
                membership__vendor=request.user
            )
            .select_related("activity")
            .order_by("-created_at", "-id")
        )

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(transactions, request, view=self)
        serializer = VendorClubTransactionSerializer(page, many=True)
        return api_response(
            data=paginator.get_paginated_response(serializer.data).data
        )
