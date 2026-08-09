from django.urls import path

from .views import (
    OrderCancelView,
    OrderConfirmPaymentView,
    OrderDetailView,
    OrderListCreateView,
    OrderPaymentMethodsView,
)

urlpatterns = [
    path("", OrderListCreateView.as_view()),
    path("payment-methods", OrderPaymentMethodsView.as_view()),
    path("<int:order_id>", OrderDetailView.as_view()),
    path("<int:order_id>/pay", OrderConfirmPaymentView.as_view()),
    path("<int:order_id>/cancel", OrderCancelView.as_view()),
]