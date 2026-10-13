from django.urls import path

from .views import VendorPackageCatalogView, VendorPackageEntitlementView
from .admin_views import (
    AdminFeatureDetail,
    AdminFeatureList,
    AdminPackageDetail,
    AdminPackageFeatureDetail,
    AdminPackageFeatureList,
    AdminPackageList,
    AdminPackagePriceHistory,
)

urlpatterns = [
    # The vendor's own entitlement, fetched by the panels at splash. Kept
    # out of the `admin/` namespace because it answers for the caller.
    path("me", VendorPackageEntitlementView.as_view()),
    # The feature/package map the panels cache to name upgrade targets.
    path("catalog", VendorPackageCatalogView.as_view()),
    path("admin/packages", AdminPackageList.as_view()),
    path("admin/packages/<int:package_id>", AdminPackageDetail.as_view()),
    path(
        "admin/packages/<int:package_id>/price-history",
        AdminPackagePriceHistory.as_view(),
    ),
    path("admin/packages/<int:package_id>/features", AdminPackageFeatureList.as_view()),
    path(
        "admin/packages/<int:package_id>/features/<int:feature_id>",
        AdminPackageFeatureDetail.as_view(),
    ),
    path("admin/features", AdminFeatureList.as_view()),
    path("admin/features/<int:feature_id>", AdminFeatureDetail.as_view()),
]
