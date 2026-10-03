from django.urls import path

from .views import (
    LandingPagePreview,
    PagePreview,
    PublicHomePage,
    PublicLandingPage,
    PublicPage,
    VendorCategoryOptionList,
    VendorComponentContractList,
    VendorLandingPageDetail,
    VendorLandingPageList,
    VendorLandingPagePreview,
    VendorLandingPagePublish,
    VendorLandingPageSEO,
    VendorPageDetail,
    VendorPageList,
    VendorPagePreview,
    VendorPagePublish,
    VendorPageSEO,
    VendorProductOptionList,
    VendorSuggestionPageList,
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
    path("vendor/landing-pages", VendorLandingPageList.as_view()),
    path(
        "vendor/landing-pages/<int:resource_id>",
        VendorLandingPageDetail.as_view(),
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/publish",
        VendorLandingPagePublish.as_view(),
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/preview",
        VendorLandingPagePreview.as_view(),
    ),
    path(
        "vendor/landing-pages/<int:resource_id>/seo",
        VendorLandingPageSEO.as_view(),
    ),
    path("vendor/pages", VendorPageList.as_view()),
    path("vendor/pages/<int:resource_id>", VendorPageDetail.as_view()),
    path("vendor/pages/<int:resource_id>/publish", VendorPagePublish.as_view()),
    path("vendor/pages/<int:resource_id>/preview", VendorPagePreview.as_view()),
    path("vendor/pages/<int:resource_id>/seo", VendorPageSEO.as_view()),
    path("vendor/options/products", VendorProductOptionList.as_view()),
    path("vendor/options/categories", VendorCategoryOptionList.as_view()),
    path("vendor/component-contracts", VendorComponentContractList.as_view()),
    path("vendor/suggestions", VendorSuggestionPageList.as_view()),
]
