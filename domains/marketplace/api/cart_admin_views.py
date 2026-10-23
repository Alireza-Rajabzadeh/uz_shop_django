"""Admin cart oversight for the marketplace basket.

The customer cart now writes marketplace tables, so the admin cart screens
must read the same tables. Permissions stay on the shop cart model because
the existing admin role already grants ``cart.view_cart`` for cart oversight.
"""

from domains.cart.admin_views import AdminCartDetail, AdminCartList

from ..services.cart_service import MarketplaceCartService


class MarketplaceAdminCartList(AdminCartList):
    cart_service_class = MarketplaceCartService


class MarketplaceAdminCartDetail(AdminCartDetail):
    cart_service_class = MarketplaceCartService
