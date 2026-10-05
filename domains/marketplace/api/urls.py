from django.urls import path

from . import admin_views, order_views, views

urlpatterns = [
    path("offers", views.BusinessOfferListCreate.as_view()),
    path("offers/<int:pk>", views.BusinessOfferDetail.as_view()),

    # Customer flow.
    path("payment-methods", order_views.MarketplacePaymentMethodsView.as_view()),
    path("returns", order_views.MarketplaceReturnRequestListCreateView.as_view()),
    path(
        "returns/<int:return_request_id>",
        order_views.MarketplaceReturnRequestDetailView.as_view(),
    ),
    path("orders", order_views.MarketplaceOrderListCreateView.as_view()),
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
]
