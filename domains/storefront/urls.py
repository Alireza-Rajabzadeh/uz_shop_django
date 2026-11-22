from django.urls import path

from .views import (
    StorefrontLayoutView,
    StorefrontPageView,
    StorefrontProductDetailView,
    StorefrontProductQuickView,
    StorefrontProductSearchView,
    StorefrontProductVariantOffersView,
)

urlpatterns = [
    # Primary Storefront APIs
    path("layout", StorefrontLayoutView.as_view(), name="layout"),
    path("home", StorefrontPageView.as_view(), name="home"),
    path("page/<str:slug>", StorefrontPageView.as_view(), name="page"),

    # Migrated Product & Discovery APIs
    path("products", StorefrontProductSearchView.as_view(), name="products"),
    path("products/<str:slug>", StorefrontProductDetailView.as_view(), name="product_detail"),
    path("products/<str:slug>/quick-view", StorefrontProductQuickView.as_view(), name="product_quick_view"),
    path(
        "products/<str:slug>/variants/<int:variant_id>/offers",
        StorefrontProductVariantOffersView.as_view(),
        name="product_variant_offers",
    ),
]
