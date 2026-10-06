"""Marketplace orders as the seller sees them.

The platform's reads sit at ``/api/marketplace/admin/orders`` behind an admin
JWT and the platform's model permissions, so a seller cannot reach them: a
vendor signs in differently and owns only their slice of the table. This
module does not reimplement that flow. It reuses the marketplace service with
the service itself narrowed to the seller's business, which scopes every
read, action and status change in the query rather than by an ownership check
around each call.

The action vocabulary is narrowed separately. The seeded action table carries
a single ``admin`` flag that also covers payment approval, refunds and
cancellation; those move money or release stock on the platform's behalf and
stay with the platform, so they are cut out of every payload and refused on
every request here.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.marketplace.api.serializers import AdminMarketplaceOrderStatusSerializer
from domains.marketplace.models import MarketplaceOrderStatus
from domains.marketplace.services.order_service import MarketplaceOrderService
from domains.marketplace.services.return_service import MarketplaceReturnRequestService
from domains.order.serializers import (
    AdminOrderListQuerySerializer,
    AdminReturnActionSerializer,
)

from ..auth import VendorJWTAuthentication
from .business import _get_business

# Fulfillment is the seller's job. Absent from this set: cancel,
# approve_payment, reject_payment and process_refund — the platform's.
VENDOR_ORDER_ACTIONS = frozenset({"confirm", "prepare", "pack", "ship", "deliver"})


class VendorOrderAPIView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _business(request):
        business = _get_business(request)
        if business is None:
            raise NotFound(_("Business profile not found."))
        return business

    @classmethod
    def _actions(cls, actions):
        """The seller's subset of an action list."""
        return [
            action for action in actions if action["code"] in VENDOR_ORDER_ACTIONS
        ]

    @classmethod
    def _payload(cls, service, order_id):
        """One order's administrative payload, minus the platform's actions."""
        payload = service.get_order_admin(order_id, include_returns=True)
        payload["available_actions"] = cls._actions(payload["available_actions"])
        return payload


class VendorOrderList(VendorOrderAPIView):
    def get(self, request):
        query = AdminOrderListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        service = MarketplaceOrderService(business=self._business(request))
        # Returns are always included: unlike the platform, a seller has no
        # permission to be denied them — every return on this list is theirs.
        rows = service.list_orders_admin(include_returns=True, **query.validated_data)
        for row in rows:
            row["available_actions"] = self._actions(row["available_actions"])
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return api_response(True, "", paginator.get_paginated_response(page).data)


class VendorOrderDetail(VendorOrderAPIView):
    def get(self, request, order_id):
        service = MarketplaceOrderService(business=self._business(request))
        try:
            payload = self._payload(service, order_id)
        except service.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        return api_response(True, "", payload)


class VendorOrderActions(VendorOrderAPIView):
    def get(self, request, order_id):
        service = MarketplaceOrderService(business=self._business(request))
        try:
            actions = service.available_actions(order_id, actor="admin")
        except service.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        return api_response(data={"actions": self._actions(actions)})


class VendorOrderExecuteAction(VendorOrderAPIView):
    def post(self, request, order_id, action_code):
        service = MarketplaceOrderService(business=self._business(request))
        if action_code not in VENDOR_ORDER_ACTIONS:
            raise ValidationError({"action": [_("This action is not available for this order.")]})
        try:
            order = service.execute_action(
                order_id, action_code, actor="admin", admin=request.user
            )
        except service.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        except service.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(data=self._payload(service, order.id))


class VendorOrderReturnAction(VendorOrderAPIView):
    def post(self, request, order_id, return_request_id, action_code):
        business = self._business(request)
        serializer = AdminReturnActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Both services are narrowed to the same business: the order service
        # reports the result, the return service refuses to decide on a
        # request that belongs to somebody else's order.
        try:
            MarketplaceReturnRequestService(business=business).execute_admin_action(
                order_id, return_request_id, action_code, **serializer.validated_data
            )
        except MarketplaceReturnRequestService.NotFoundError as exc:
            raise NotFound(_("Return request not found.")) from exc
        except MarketplaceReturnRequestService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        service = MarketplaceOrderService(business=business)
        try:
            payload = self._payload(service, order_id)
        except service.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        return api_response(data=payload)


class VendorOrderStatusList(VendorOrderAPIView):
    # Statuses only populate the order filters, so they need no business.
    def get(self, request):
        statuses = MarketplaceOrderStatus.objects.order_by("id")
        return api_response(
            True, "", AdminMarketplaceOrderStatusSerializer(statuses, many=True).data
        )
