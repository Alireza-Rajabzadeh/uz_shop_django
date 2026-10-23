"""Customer cart endpoints for the marketplace basket.

The cart behaviour is the shared cart behaviour; only the tables differ, so
each shop cart view is subclassed with the marketplace service. This keeps the
shop cart endpoints available to the legacy flow while every customer cart
write lands in ``marketplace_cart``.
"""

from domains.cart.views import (
    CartAddressView,
    CartClearView,
    CartItemDetail,
    CartItemMoveToPreOrder,
    CartItemMoveToWishlist,
    CartItemsView,
    CartMergeView,
    CartSyncView,
    CartValidateItemsView,
    CartValidateView,
    CartView,
)

from ..services.cart_service import MarketplaceCartService


class MarketplaceCartView(CartView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemsView(CartItemsView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemDetail(CartItemDetail):
    cart_service_class = MarketplaceCartService


class MarketplaceCartClearView(CartClearView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartAddressView(CartAddressView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemMoveToWishlist(CartItemMoveToWishlist):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemMoveToPreOrder(CartItemMoveToPreOrder):
    cart_service_class = MarketplaceCartService


class MarketplaceCartSyncView(CartSyncView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartValidateView(CartValidateView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartValidateItemsView(CartValidateItemsView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartMergeView(CartMergeView):
    cart_service_class = MarketplaceCartService
