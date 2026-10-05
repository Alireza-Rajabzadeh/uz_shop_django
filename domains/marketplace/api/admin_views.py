"""Administrative endpoints for marketplace orders.

The admin reads, action execution and return decisions are the shop's
endpoints over the marketplace tables. The permission check on each view is
derived from ``model``, so an admin needs ``marketplace.view_marketplaceorder``
rather than the shop's own order permission to see this list.
"""

from domains.order.admin_views import (
    AdminOrderActions,
    AdminOrderDetail,
    AdminOrderExecuteAction,
    AdminOrderList,
    AdminOrderStatusList,
    AdminReturnAction,
)

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
)
from ..services.order_service import MarketplaceOrderService
from ..services.return_service import MarketplaceReturnRequestService
from .serializers import AdminMarketplaceOrderStatusSerializer


class MarketplaceAdminOrderList(AdminOrderList):
    model = MarketplaceOrder
    order_service_class = MarketplaceOrderService
    return_service_class = MarketplaceReturnRequestService


class MarketplaceAdminOrderDetail(AdminOrderDetail):
    model = MarketplaceOrder
    order_service_class = MarketplaceOrderService
    return_service_class = MarketplaceReturnRequestService


class MarketplaceAdminOrderStatusList(AdminOrderStatusList):
    model = MarketplaceOrderStatus
    status_model = MarketplaceOrderStatus
    status_serializer = AdminMarketplaceOrderStatusSerializer


class MarketplaceAdminOrderActions(AdminOrderActions):
    model = MarketplaceOrder
    order_service_class = MarketplaceOrderService
    return_service_class = MarketplaceReturnRequestService


class MarketplaceAdminOrderExecuteAction(AdminOrderExecuteAction):
    model = MarketplaceOrder
    order_service_class = MarketplaceOrderService
    return_service_class = MarketplaceReturnRequestService


class MarketplaceAdminReturnAction(AdminReturnAction):
    model = MarketplaceReturnRequest
    order_service_class = MarketplaceOrderService
    return_service_class = MarketplaceReturnRequestService
