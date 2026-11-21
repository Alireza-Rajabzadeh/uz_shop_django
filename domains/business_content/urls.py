from django.urls import path

from .views import (
    LandingPagePreview,
    PagePreview,
    PublicHomePage,
    PublicLandingPage,
    PublicPage,
    VendorContentOptionsView,
    VendorLandingPageView,
    VendorPageView,
    VendorSEOView,
)

urlpatterns = [
    # Public delivery. These serve the singleton business profile's rows;
    # the platform storefront's own content stays under /api/content/.
    path("home", PublicHomePage.as_view()),
    path("landing-pages/<str:slug>/preview", LandingPagePreview.as_view()),
    path("landing-pages/<str:slug>", PublicLandingPage.as_view()),
    path("pages/<str:slug>/preview", PagePreview.as_view()),
    path("pages/<str:slug>", PublicPage.as_view()),

    # Business authoring. The `vendor/` prefix keeps `<int:id>` detail routes
    # unambiguous against the `<str:slug>` delivery routes above.
    path("vendor/landing-pages", VendorLandingPageView.as_view()),
    path(
        "vendor/landing-pages/<int:resource_id>",
        VendorLandingPageView.as_view(),
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/publish",
        VendorLandingPageView.as_view(),
        {"action": "publish"},
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/preview",
        VendorLandingPageView.as_view(),
        {"action": "preview"},
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/seo",
        VendorSEOView.as_view(),
        {"resource_type": "landing_page"},
    ),

    path("vendor/pages", VendorPageView.as_view()),
    path("vendor/pages/<int:resource_id>", VendorPageView.as_view()),
    path(
        "vendor/pages/<int:resource_id>/publish",
        VendorPageView.as_view(),
        {"action": "publish"},
    ),
    path(
        "vendor/pages/<int:resource_id>/preview",
        VendorPageView.as_view(),
        {"action": "preview"},
    ),
    path(
        "vendor/pages/<int:resource_id>/seo",
        VendorSEOView.as_view(),
        {"resource_type": "page"},
    ),

    path(
        "vendor/options/products",
        VendorContentOptionsView.as_view(),
        {"option_type": "products"},
    ),
    path(
        "vendor/options/categories",
        VendorContentOptionsView.as_view(),
        {"option_type": "categories"},
    ),
    path(
        "vendor/component-contracts",
        VendorContentOptionsView.as_view(),
        {"option_type": "contracts"},
    ),
    path(
        "vendor/suggestions",
        VendorContentOptionsView.as_view(),
        {"option_type": "suggestions"},
    ),
]
