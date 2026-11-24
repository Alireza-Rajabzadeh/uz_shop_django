from core.services import CacheService
from ..services.landing_page_content_resolver import LandingPageContentResolver

from .admin_landing_page import AdminLandingPageView
from .admin_page import AdminPageView
from .admin_seo import AdminSEOView
from .options import (
    AdminContentOptionsView,
    read_component_contracts,
    serialize_category_option,
    serialize_product_option,
)
from .public import (
    LandingPageBySlug,
    PublicLandingPage,
)

# Aliases for backward compatibility
AdminLandingPageList = AdminLandingPageView
AdminLandingPageDetail = AdminLandingPageView
AdminLandingPagePublish = AdminLandingPageView
AdminLandingPageSEO = AdminSEOView

AdminPageList = AdminPageView
AdminPageDetail = AdminPageView
AdminPagePublish = AdminPageView
AdminPageSEO = AdminSEOView

AdminProductSEO = AdminSEOView
AdminCategorySEO = AdminSEOView
AdminBrandSEO = AdminSEOView

AdminContentComponentContractList = AdminContentOptionsView
AdminProductOptionList = AdminContentOptionsView
AdminCategoryOptionList = AdminContentOptionsView

__all__ = [
    "AdminBrandSEO",
    "AdminCategoryOptionList",
    "AdminCategorySEO",
    "AdminContentComponentContractList",
    "AdminContentOptionsView",
    "AdminLandingPageDetail",
    "AdminLandingPageList",
    "AdminLandingPagePublish",
    "AdminLandingPageSEO",
    "AdminLandingPageView",
    "AdminPageDetail",
    "AdminPageList",
    "AdminPagePublish",
    "AdminPageSEO",
    "AdminPageView",
    "AdminProductOptionList",
    "AdminProductSEO",
    "AdminSEOView",
    "CacheService",
    "LandingPageBySlug",
    "LandingPageContentResolver",
    "PublicLandingPage",
    "read_component_contracts",
    "serialize_category_option",
    "serialize_product_option",
]
