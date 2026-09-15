from django.urls import path

from .views import (
    AdminBusinessCategoryView,
    PhoneDetail, PhoneList, ProfileDetail, ProfileList, PublicBusinessView,
    PublicSocialMediaListView, SocialLinkDetail, SocialLinkList,
    SocialMediaDetail, SocialMediaIconDetail, SocialMediaIconList, SocialMediaList,
    WorkingDayDetail, WorkingDayList,
)

urlpatterns = [
    path("public", PublicBusinessView.as_view(), name="business-public"),
    path("public/social-medias", PublicSocialMediaListView.as_view(), name="business-public-social-medias"),
    path("admin/profile", ProfileList.as_view(), name="business-profile-list"),
    path("admin/profile/<int:pk>", ProfileDetail.as_view(), name="business-profile-detail"),
    path("admin/phones", PhoneList.as_view(), name="business-phone-list"),
    path("admin/phones/<int:pk>", PhoneDetail.as_view(), name="business-phone-detail"),
    path("admin/social-links", SocialLinkList.as_view(), name="business-social-link-list"),
    path("admin/social-links/<int:pk>", SocialLinkDetail.as_view(), name="business-social-link-detail"),
    path("admin/social-medias", SocialMediaList.as_view(), name="business-social-media-list"),
    path("admin/social-medias/<int:pk>", SocialMediaDetail.as_view(), name="business-social-media-detail"),
    path("admin/social-medias/<int:pk>/icons", SocialMediaIconList.as_view(), name="business-social-media-icon-list"),
    path("admin/social-medias/<int:pk>/icons/<int:icon_pk>", SocialMediaIconDetail.as_view(), name="business-social-media-icon-detail"),
    path("admin/working-days", WorkingDayList.as_view(), name="business-working-day-list"),
    path("admin/working-days/<int:pk>", WorkingDayDetail.as_view(), name="business-working-day-detail"),
    path("admin/categories", AdminBusinessCategoryView.as_view(), name="business-categories"),
]
