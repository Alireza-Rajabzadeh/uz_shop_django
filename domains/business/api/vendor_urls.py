from django.urls import path

from .views import (
    VendorBusinessChargeDetailView,
    VendorBusinessChargeListCreateView,
    VendorBusinessChargeStatusView,
)

urlpatterns = [
    path("charges", VendorBusinessChargeListCreateView.as_view(), name="business-charge-list"),
    path("charges/<int:pk>", VendorBusinessChargeDetailView.as_view(), name="business-charge-detail"),
    path(
        "charges/<int:pk>/<str:action>",
        VendorBusinessChargeStatusView.as_view(),
        name="business-charge-status",
    ),
]
