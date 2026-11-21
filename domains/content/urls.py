from django.urls import path

from .views import (
    AdminContentOptionsView,
    AdminLandingPageView,
    AdminPageView,
    AdminSEOView,
    LandingPagePreview,
    PagePreview,
    PublicHomePage,
    PublicLandingPage,
    PublicPage,
    PublicResourceSEO,
)

urlpatterns = [
    # Public Storefront & Delivery
    path("home", PublicHomePage.as_view()),
    path("landing-pages/<str:slug>/preview", LandingPagePreview.as_view()),
    path("landing-pages/<str:slug>", PublicLandingPage.as_view()),
    path("pages/<str:slug>/preview", PagePreview.as_view()),
    path("pages/<str:slug>", PublicPage.as_view()),
    path("seo/<str:resource_type>/<str:slug>", PublicResourceSEO.as_view()),

    # Admin Landing Pages
    path("admin/landing-pages", AdminLandingPageView.as_view()),
    path("admin/landing-pages/<int:landing_page_id>", AdminLandingPageView.as_view()),
    path(
        "admin/landing-pages/<int:landing_page_id>/publish",
        AdminLandingPageView.as_view(),
        {"action": "publish"},
    ),

    # Admin Pages
    path("admin/pages", AdminPageView.as_view()),
    path("admin/pages/<int:page_id>", AdminPageView.as_view()),
    path(
        "admin/pages/<int:page_id>/publish",
        AdminPageView.as_view(),
        {"action": "publish"},
    ),

    # Admin SEO
    path(
        "admin/landing-pages/<int:resource_id>/seo",
        AdminSEOView.as_view(),
        {"resource_type": "landing_page"},
    ),
    path(
        "admin/pages/<int:resource_id>/seo",
        AdminSEOView.as_view(),
        {"resource_type": "page"},
    ),
    path(
        "admin/products/<int:resource_id>/seo",
        AdminSEOView.as_view(),
        {"resource_type": "product"},
    ),
    path(
        "admin/categories/<int:resource_id>/seo",
        AdminSEOView.as_view(),
        {"resource_type": "category"},
    ),
    path(
        "admin/brands/<int:resource_id>/seo",
        AdminSEOView.as_view(),
        {"resource_type": "brand"},
    ),

    # Admin Options & Contracts
    path(
        "admin/component-contracts",
        AdminContentOptionsView.as_view(),
        {"option_type": "contracts"},
    ),
    path(
        "admin/options/products",
        AdminContentOptionsView.as_view(),
        {"option_type": "products"},
    ),
    path(
        "admin/options/categories",
        AdminContentOptionsView.as_view(),
        {"option_type": "categories"},
    ),
]
