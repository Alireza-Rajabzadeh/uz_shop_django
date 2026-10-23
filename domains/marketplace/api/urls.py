from django.urls import path

from . import admin_views, cart_admin_views, cart_views, order_views, views

urlpatterns = [
    path("offers", views.BusinessOfferListCreate.as_view()),
    path("offers/<int:pk>", views.BusinessOfferDetail.as_view()),

    # Customer cart.
    path("cart/", cart_views.MarketplaceCartView.as_view()),
    path("cart/items", cart_views.MarketplaceCartItemsView.as_view()),
    path("cart/sync", cart_views.MarketplaceCartSyncView.as_view()),
    path("cart/clear", cart_views.MarketplaceCartClearView.as_view()),
    path("cart/merge", cart_views.MarketplaceCartMergeView.as_view()),
    path("cart/address", cart_views.MarketplaceCartAddressView.as_view()),
    path("cart/validate", cart_views.MarketplaceCartValidateView.as_view()),
    path(
        "cart/validate-items",
        cart_views.MarketplaceCartValidateItemsView.as_view(),
    ),
    path(
        "cart/items/<int:item_id>",
        cart_views.MarketplaceCartItemDetail.as_view(),
    ),
    path(
        "cart/items/<int:item_id>/move-to-wishlist",
        cart_views.MarketplaceCartItemMoveToWishlist.as_view(),
    ),
    path(
        "cart/items/<int:item_id>/move-to-preorder",
        cart_views.MarketplaceCartItemMoveToPreOrder.as_view(),
    ),

    # Customer flow.
    path(
        "orders/<int:order_id>/payment-methods",
        order_views.MarketplaceOrderPaymentMethodsView.as_view(),
    ),
    path("returns", order_views.MarketplaceReturnRequestListCreateView.as_view()),
    path(
        "returns/<int:return_request_id>",
        order_views.MarketplaceReturnRequestDetailView.as_view(),
    ),
    path("orders/", order_views.MarketplaceOrderListCreateView.as_view()),
    path("orders/<int:order_id>", order_views.MarketplaceOrderDetailView.as_view()),
    path(
        "orders/<int:order_id>/pay",
        order_views.MarketplaceOrderConfirmPaymentView.as_view(),
    ),
    path(
        "orders/<int:order_id>/actions",
        order_views.MarketplaceOrderActionsView.as_view(),
    ),
    path(
        "orders/<int:order_id>/actions/<str:action_code>",
        order_views.MarketplaceOrderExecuteActionView.as_view(),
    ),
    path(
        "orders/<int:order_id>/cancel",
        order_views.MarketplaceOrderCancelView.as_view(),
    ),

    # Administrative flow.
    path(
        "admin/carts",
        cart_admin_views.MarketplaceAdminCartList.as_view(),
    ),
    path(
        "admin/carts/<int:cart_id>",
        cart_admin_views.MarketplaceAdminCartDetail.as_view(),
    ),
    path("admin/orders", admin_views.MarketplaceAdminOrderList.as_view()),
    path(
        "admin/orders/<int:order_id>",
        admin_views.MarketplaceAdminOrderDetail.as_view(),
    ),
    path(
        "admin/orders/<int:order_id>/actions",
        admin_views.MarketplaceAdminOrderActions.as_view(),
    ),
    path(
        "admin/orders/<int:order_id>/actions/<str:action_code>",
        admin_views.MarketplaceAdminOrderExecuteAction.as_view(),
    ),
    path(
        "admin/orders/<int:order_id>/returns/<int:return_request_id>/actions/<str:action_code>",
        admin_views.MarketplaceAdminReturnAction.as_view(),
    ),
    path("admin/statuses", admin_views.MarketplaceAdminOrderStatusList.as_view()),
    path("admin/businesses", admin_views.MarketplaceAdminBusinessList.as_view()),
]
