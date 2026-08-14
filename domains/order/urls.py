from django.urls import path

from .admin_views import (
    AdminOrderDetail,
    AdminOrderActions,
    AdminOrderExecuteAction,
    AdminOrderList,
    AdminOrderStatusList,
)
from .views import (
    OrderCancelView,
    OrderActionsView,
    OrderConfirmPaymentView,
    OrderDetailView,
    OrderListCreateView,
    OrderPaymentMethodsView,
    OrderExecuteActionView,
)

urlpatterns = [
    path("", OrderListCreateView.as_view()),
    path("admin/orders", AdminOrderList.as_view()),
    path("admin/orders/<int:order_id>", AdminOrderDetail.as_view()),
    path("admin/orders/<int:order_id>/actions", AdminOrderActions.as_view()),
    path(
        "admin/orders/<int:order_id>/actions/<str:action_code>",
        AdminOrderExecuteAction.as_view(),
    ),
    path("admin/statuses", AdminOrderStatusList.as_view()),
    path("payment-methods", OrderPaymentMethodsView.as_view()),
    path("<int:order_id>", OrderDetailView.as_view()),
    path("<int:order_id>/pay", OrderConfirmPaymentView.as_view()),
    path("<int:order_id>/actions", OrderActionsView.as_view()),
    path(
        "<int:order_id>/actions/<str:action_code>",
        OrderExecuteActionView.as_view(),
    ),
    path("<int:order_id>/cancel", OrderCancelView.as_view()),
]
