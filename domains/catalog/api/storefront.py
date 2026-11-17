"""Backward-compatibility shim.

Customer-facing storefront presentation views have migrated to `domains.storefront`.
This module re-exports the migrated views to maintain backwards compatibility for
existing routes and references.
"""

from domains.storefront.views import (
    StorefrontProductDetailView as StorefrontProductDetail,
    StorefrontProductQuickView,
    StorefrontProductSearchView as StorefrontProductSearch,
    StorefrontProductVariantOffersView as StorefrontProductVariantOffers,
    StorefrontStaticDataView as StorefrontStaticData,
)

__all__ = [
    "StorefrontStaticData",
    "StorefrontProductSearch",
    "StorefrontProductQuickView",
    "StorefrontProductDetail",
    "StorefrontProductVariantOffers",
]
