"""Customer endpoints for marketplace orders.

Every class below is one of the shop's order views with the flow swapped,
because a marketplace customer's basket, hold, payment and return go through
exactly the same steps — only the rows they land on differ. The envelopes,
status codes and error shapes therefore stay identical between the two.
"""

from domains.order.views import (
    OrderActionsView,
    OrderCancelView,
    OrderConfirmPaymentView,
    OrderDetailView,
    OrderExecuteActionView,
    OrderListCreateView,
    OrderPaymentMethodsView,
    ReturnRequestDetailView,
    ReturnRequestListCreateView,
)

from ..services.order_service import MarketplaceOrderService
from ..services.payment_service import MarketplacePaymentService
from ..services.return_service import MarketplaceReturnRequestService
from .serializers import (
    MarketplaceReturnRequestCreateSerializer,
    MarketplaceReturnRequestSerializer,
)


class MarketplaceOrderListCreateView(OrderListCreateView):
    order_service_class = MarketplaceOrderService


class MarketplaceOrderDetailView(OrderDetailView):
    order_service_class = MarketplaceOrderService


class MarketplacePaymentMethodsView(OrderPaymentMethodsView):
    payment_service_class = MarketplacePaymentService


class MarketplaceOrderConfirmPaymentView(OrderConfirmPaymentView):
    payment_service_class = MarketplacePaymentService
    order_service_class = MarketplaceOrderService


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
