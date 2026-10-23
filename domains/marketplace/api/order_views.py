"""Customer endpoints for marketplace orders.

Every class below is one of the shop's order views with the flow swapped,
because a marketplace customer's basket, hold, payment and return go through
exactly the same steps — only the rows they land on differ. The envelopes,
status codes and error shapes therefore stay identical between the two.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response
from domains.order.views import (
    OrderActionsView,
    OrderCancelView,
    OrderConfirmPaymentView,
    OrderDetailView,
    OrderExecuteActionView,
    OrderListCreateView,
    ReturnRequestDetailView,
    ReturnRequestListCreateView,
)
from domains.payments.serializers import ConfirmPaymentSerializer

from ..models import MarketplaceOrder
from ..services.order_service import MarketplaceOrderService
from ..services.payment_service import MarketplacePaymentService
from ..services.return_service import MarketplaceReturnRequestService
from .serializers import (
    MarketplaceCheckoutSerializer,
    MarketplaceReturnRequestCreateSerializer,
    MarketplaceReturnRequestSerializer,
)


def _business_ref(business):
    return {
        "id": business.id,
        "name": business.display_name or business.business_name,
    }


class MarketplaceOrderListCreateView(OrderListCreateView):
    order_service_class = MarketplaceOrderService

    def post(self, request):
        serializer = MarketplaceCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self.order_service_class()
        try:
            order = service.checkout_business_from_cart(
                request.user, serializer.validated_data["business_id"]
            )
        except service.PaymentMethodUnavailable as exc:
            return api_response(
                False,
                str(exc),
                {
                    "code": "payment_method_unavailable",
                    "business": _business_ref(exc.business),
                },
                {"payment_method": [str(exc)]},
                status_code=409,
            )
        except service.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Order created."),
            service._customer_order_payload(order),
            status_code=201,
        )


class MarketplaceOrderDetailView(OrderDetailView):
    order_service_class = MarketplaceOrderService


class MarketplaceOrderPaymentMethodsView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request, order_id):
        order = (
            MarketplaceOrder.objects.select_related("business")
            .filter(id=order_id, customer=request.user)
            .first()
        )
        if order is None:
            raise NotFound("Order not found.")
        methods = MarketplacePaymentService().customer_methods_payload(
            business_id=order.business_id
        )
        return api_response(
            data={
                "business": _business_ref(order.business),
                "methods": methods,
            }
        )


class MarketplaceOrderConfirmPaymentView(OrderConfirmPaymentView):
    payment_service_class = MarketplacePaymentService
    order_service_class = MarketplaceOrderService

    def post(self, request, order_id):
        serializer = ConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            order = (
                self.payment_service_class().confirm_manual_payment_for_customer(
                    request.user,
                    order_id,
                    payment_method_code=data["payment_method"],
                    payment_channel_id=data["payment_channel_id"],
                    ref_number=data.get("ref_number"),
                    resource_account_number=data.get("resource_account_number"),
                    documents=data.get("documents", []),
                )
            )
        except self.payment_service_class.NotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except self.payment_service_class.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Payment submitted for review."),
            self.order_service_class()._customer_order_payload(order),
            status_code=202,
        )


class MarketplaceOrderActionsView(OrderActionsView):
    order_service_class = MarketplaceOrderService


class MarketplaceOrderExecuteActionView(OrderExecuteActionView):
    order_service_class = MarketplaceOrderService


class MarketplaceOrderCancelView(OrderCancelView):
    order_service_class = MarketplaceOrderService


class MarketplaceReturnRequestListCreateView(ReturnRequestListCreateView):
    return_service_class = MarketplaceReturnRequestService
    create_serializer = MarketplaceReturnRequestCreateSerializer
    read_serializer = MarketplaceReturnRequestSerializer


class MarketplaceReturnRequestDetailView(ReturnRequestDetailView):
    return_service_class = MarketplaceReturnRequestService
    read_serializer = MarketplaceReturnRequestSerializer
