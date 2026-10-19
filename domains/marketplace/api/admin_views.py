"""Administrative endpoints for marketplace orders.

The admin reads, action execution and return decisions are the shop's
endpoints over the marketplace tables. The permission check on each view is
derived from ``model``, so an admin needs ``marketplace.view_marketplaceorder``
rather than the shop's own order permission to see this list.
"""

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.order.admin_views import (
    AdminAPIView,
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


class MarketplaceAdminBusinessList(AdminAPIView):
    """Business choices for the marketplace order filter.

    Gated by ``marketplace.view_marketplaceorder`` through ``model`` rather
    than ``business.view_businessprofile``, so an order operator can filter the
    list without holding the business module's read permission.
    """

    model = MarketplaceOrder

    def get(self, request):
        businesses = BusinessProfile.objects.order_by("id")
        return api_response(
            True,
            "",
            [
                {
                    "id": business.id,
                    "name": business.display_name or business.business_name,
                }
                for business in businesses
            ],
        )


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
