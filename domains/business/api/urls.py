from django.urls import path

from .views import PhoneDetail, PhoneList, ProfileDetail, ProfileList, PublicBusinessView, SocialLinkDetail, SocialLinkList, WorkingDayDetail, WorkingDayList

urlpatterns = [
    path("public", PublicBusinessView.as_view(), name="business-public"),
    path("admin/profile", ProfileList.as_view(), name="business-profile-list"),
    path("admin/profile/<int:pk>", ProfileDetail.as_view(), name="business-profile-detail"),
    path("admin/phones", PhoneList.as_view(), name="business-phone-list"),
    path("admin/phones/<int:pk>", PhoneDetail.as_view(), name="business-phone-detail"),
    path("admin/social-links", SocialLinkList.as_view(), name="business-social-link-list"),
    path("admin/social-links/<int:pk>", SocialLinkDetail.as_view(), name="business-social-link-detail"),
    path("admin/working-days", WorkingDayList.as_view(), name="business-working-day-list"),
    path("admin/working-days/<int:pk>", WorkingDayDetail.as_view(), name="business-working-day-detail"),
]
