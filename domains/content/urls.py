from django.urls import path

from .views import (
    AdminCategoryOptionList,
    AdminContentComponentContractList,
    AdminLandingPageDetail,
    AdminLandingPageList,
    AdminProductOptionList,
    LandingPagePreview,
    PublicLandingPage,
)

urlpatterns = [
    path("admin/landing-pages", AdminLandingPageList.as_view()),
    path("admin/landing-pages/<int:landing_page_id>", AdminLandingPageDetail.as_view()),
    path("admin/component-contracts", AdminContentComponentContractList.as_view()),
    path("admin/options/products", AdminProductOptionList.as_view()),
    path("admin/options/categories", AdminCategoryOptionList.as_view()),
    path("landing-pages/<str:slug>/preview", LandingPagePreview.as_view()),
    path("landing-pages/<str:slug>", PublicLandingPage.as_view()),
]
