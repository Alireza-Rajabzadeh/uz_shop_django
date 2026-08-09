from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.order.models import Order, OrderStatus
from domains.order.serializers import (
    AdminOrderListQuerySerializer,
    AdminOrderStatusSerializer,
)
from domains.order.services import OrderService
from domains.users.auth import AdminJWTAuthentication


order_service = OrderService()


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminOrderList(AdminAPIView):
    model = Order

    def get(self, request):
        query = AdminOrderListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        orders = order_service.list_orders_admin(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(orders, request, view=self)
        return api_response(
            True, "", paginator.get_paginated_response(page).data
        )


class AdminOrderDetail(AdminAPIView):
    model = Order

    def get(self, request, order_id):
        try:
            payload = order_service.get_order_admin(order_id)
        except OrderService.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        return api_response(True, "", payload)


class AdminOrderStatusList(AdminAPIView):
    # Statuses are supporting options for the admin order filters, so viewing
    # orders is sufficient to populate this endpoint.
    model = OrderStatus

    def get(self, request):
        statuses = OrderStatus.objects.order_by("id")
        return api_response(True, "", AdminOrderStatusSerializer(statuses, many=True).data)
