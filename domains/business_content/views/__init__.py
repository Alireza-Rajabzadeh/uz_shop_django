from core.services import CacheService
from ..services.landing_page_content_resolver import LandingPageContentResolver

from .options import (
    VendorContentOptionsView,
    read_component_contracts,
    serialize_category_option,
    serialize_product_option,
)
from .public import (
    LandingPageBySlug,
    LandingPagePreview,
    PageBySlug,
    PagePreview,
    PublicHomePage,
    PublicLandingPage,
    PublicPage,
)
from .vendor_landing_page import VendorLandingPageView
from .vendor_page import VendorPageView
from .vendor_seo import VendorSEOView

# Backward compatibility aliases
VendorLandingPageList = VendorLandingPageView
VendorLandingPageDetail = VendorLandingPageView
VendorLandingPagePublish = VendorLandingPageView
VendorLandingPagePreview = VendorLandingPageView
VendorLandingPageSEO = VendorSEOView

VendorPageList = VendorPageView
VendorPageDetail = VendorPageView
VendorPagePublish = VendorPageView
VendorPagePreview = VendorPageView
VendorPageSEO = VendorSEOView

VendorProductOptionList = VendorContentOptionsView
VendorCategoryOptionList = VendorContentOptionsView
VendorComponentContractList = VendorContentOptionsView
VendorSuggestionPageList = VendorContentOptionsView

__all__ = [
    "CacheService",
    "LandingPageBySlug",
    "LandingPageContentResolver",
    "LandingPagePreview",
    "PageBySlug",
    "PagePreview",
    "PublicHomePage",
    "PublicLandingPage",
    "PublicPage",
    "VendorCategoryOptionList",
    "VendorComponentContractList",
    "VendorContentOptionsView",
    "VendorLandingPageDetail",
    "VendorLandingPageList",
    "VendorLandingPagePreview",
    "VendorLandingPagePublish",
    "VendorLandingPageSEO",
    "VendorLandingPageView",
    "VendorPageDetail",
    "VendorPageList",
    "VendorPagePreview",
    "VendorPagePublish",
    "VendorPageSEO",
    "VendorPageView",
    "VendorProductOptionList",
    "VendorSEOView",
    "VendorSuggestionPageList",
    "read_component_contracts",
    "serialize_category_option",
    "serialize_product_option",
]
