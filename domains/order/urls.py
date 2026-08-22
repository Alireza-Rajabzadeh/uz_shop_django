from django.urls import path

from .admin_views import (
    AdminOrderDetail,
    AdminOrderActions,
    AdminOrderExecuteAction,
    AdminOrderList,
    AdminOrderStatusList,
    AdminReturnAction,
)
from .views import (
    OrderCancelView,
    OrderActionsView,
    OrderConfirmPaymentView,
    OrderDetailView,
    OrderListCreateView,
    OrderPaymentMethodsView,
    OrderExecuteActionView,
    ReturnRequestDetailView,
    ReturnRequestListCreateView,
)

urlpatterns = [
    path("", OrderListCreateView.as_view()),
    path("admin/orders", AdminOrderList.as_view()),
    path("admin/orders/<int:order_id>", AdminOrderDetail.as_view()),
    path("admin/orders/<int:order_id>/actions", AdminOrderActions.as_view()),
    path(
        "admin/orders/<int:order_id>/returns/<int:return_request_id>/actions/<str:action_code>",
        AdminReturnAction.as_view(),
    ),
    path(
        "admin/orders/<int:order_id>/actions/<str:action_code>",
        AdminOrderExecuteAction.as_view(),
    ),
    path("admin/statuses", AdminOrderStatusList.as_view()),
    path("payment-methods", OrderPaymentMethodsView.as_view()),
    path("returns", ReturnRequestListCreateView.as_view()),
    path("returns/<int:return_request_id>", ReturnRequestDetailView.as_view()),
    path("<int:order_id>", OrderDetailView.as_view()),
    path("<int:order_id>/pay", OrderConfirmPaymentView.as_view()),
    path("<int:order_id>/actions", OrderActionsView.as_view()),
    path(
        "<int:order_id>/actions/<str:action_code>",
        OrderExecuteActionView.as_view(),
    ),
    path("<int:order_id>/cancel", OrderCancelView.as_view()),
]
