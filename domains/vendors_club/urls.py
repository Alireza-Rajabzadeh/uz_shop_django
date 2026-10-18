from django.urls import path

from .admin_views import (
    AdminVendorClubActivityDetail,
    AdminVendorClubActivityList,
    AdminVendorClubMembershipDetail,
    AdminVendorClubMembershipList,
    AdminVendorClubMembershipResync,
    AdminVendorClubOverview,
    AdminVendorClubTransactionDetail,
    AdminVendorClubTransactionList,
)

urlpatterns = [
    path("admin/activities", AdminVendorClubActivityList.as_view()),
    path(
        "admin/activities/<int:activity_id>",
        AdminVendorClubActivityDetail.as_view(),
    ),
    path("admin/memberships", AdminVendorClubMembershipList.as_view()),
    path(
        "admin/memberships/<int:membership_id>",
        AdminVendorClubMembershipDetail.as_view(),
    ),
    path(
        "admin/memberships/<int:membership_id>/resync",
        AdminVendorClubMembershipResync.as_view(),
    ),
    path("admin/transactions", AdminVendorClubTransactionList.as_view()),
    path(
        "admin/transactions/<int:transaction_id>",
        AdminVendorClubTransactionDetail.as_view(),
    ),
    path("admin/overview", AdminVendorClubOverview.as_view()),
]
