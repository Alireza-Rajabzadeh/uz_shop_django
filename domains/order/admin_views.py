from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.order.models import Order, OrderStatus, ReturnRequest
from domains.order.serializers import (
    AdminOrderListQuerySerializer,
    AdminOrderStatusSerializer,
    AdminReturnActionSerializer,
)
from domains.order.services import OrderService, ReturnRequestService
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
        can_view_returns = request.user.has_perm("order.view_returnrequest")
        if query.validated_data["has_active_returns"] and not can_view_returns:
            raise PermissionDenied(_("You do not have permission to view return requests."))
        orders = order_service.list_orders_admin(
            include_returns=can_view_returns,
            **query.validated_data,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(orders, request, view=self)
        return api_response(
            True, "", paginator.get_paginated_response(page).data
        )


class AdminOrderGeography(AdminAPIView):
    model = Order

    def get(self, request):
        query = AdminOrderListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return api_response(data=order_service.open_order_geography(**query.validated_data))


class AdminOrderDetail(AdminAPIView):
    model = Order

    def get(self, request, order_id):
        try:
            payload = order_service.get_order_admin(
                order_id,
                include_returns=request.user.has_perm("order.view_returnrequest"),
            )
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


class AdminOrderActionPermissions(AdminModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.change_%(model_name)s"],
    }


class AdminOrderActions(AdminAPIView):
    model = Order
    permission_classes = [AdminOrderActionPermissions]

    def get(self, request, order_id):
        try:
            actions = order_service.available_actions(order_id, actor="admin")
        except OrderService.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        return api_response(data={"actions": actions})


class AdminOrderExecuteAction(AdminAPIView):
    model = Order
    permission_classes = [AdminOrderActionPermissions]

    def post(self, request, order_id, action_code):
        try:
            order = order_service.execute_action(
                order_id, action_code, actor="admin", admin=request.user
            )
        except OrderService.NotFoundError as exc:
            raise NotFound(_("Order not found.")) from exc
        except OrderService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(data=order_service.get_order_admin(
            order.id,
            include_returns=request.user.has_perm("order.view_returnrequest"),
        ))


class AdminReturnAction(AdminAPIView):
    model = ReturnRequest
    permission_classes = [AdminOrderActionPermissions]

    def post(self, request, order_id, return_request_id, action_code):
        serializer = AdminReturnActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kwargs = serializer.validated_data
        try:
            ReturnRequestService().execute_admin_action(
                order_id, return_request_id, action_code, **kwargs
            )
        except ReturnRequestService.NotFoundError as exc:
            raise NotFound(_("Return request not found.")) from exc
        except ReturnRequestService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(data=order_service.get_order_admin(
            order_id,
            include_returns=request.user.has_perm("order.view_returnrequest"),
        ))
