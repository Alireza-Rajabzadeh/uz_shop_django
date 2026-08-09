from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response

from .serializers import ConfirmPaymentSerializer
from .services import OrderService


def _map_errors(exc):
    raise ValidationError(exc.errors) from exc


class OrderListCreateView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        orders = OrderService().list_orders(request.user)
        data = {
            "count": len(orders),
            "results": orders,
        }
        return api_response(True, "", data)

    def post(self, request):
        try:
            order = OrderService().checkout_from_cart(request.user)
        except OrderService.ValidationError as exc:
            _map_errors(exc)
        payload = OrderService()._order_payload(order)
        return api_response(True, _("Order created."), payload, status_code=201)


class OrderDetailView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, order_id):
        try:
            payload = OrderService().get_order(request.user, order_id)
        except OrderService.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return api_response(True, "", payload)


class OrderPaymentMethodsView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        return api_response(True, "", {"methods": OrderService().payment_methods_payload()})


class OrderConfirmPaymentView(APIView):
    permission_classes = [IsCustomer]

    def _order(self, request, order_id):
        try:
            return OrderService()._get_customer_order(request.user, order_id)
        except OrderService.NotFoundError as exc:
            raise NotFound(str(exc)) from exc

    def post(self, request, order_id):
        serializer = ConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            order = OrderService().confirm_manual_payment(
                request.user,
                order_id,
                payment_method_name=data["payment_method"],
                payment_channel_id=data["payment_channel_id"],
                ref_number=data.get("ref_number"),
                resource_account_number=data.get("resource_account_number"),
            )
        except OrderService.ValidationError as exc:
            _map_errors(exc)
        payload = OrderService()._order_payload(order)
        return api_response(True, _("Payment confirmed."), payload)


class OrderCancelView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request, order_id):
        try:
            order = OrderService().cancel_order(request.user, order_id)
        except OrderService.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except OrderService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Order cancelled."), OrderService()._order_payload(order))