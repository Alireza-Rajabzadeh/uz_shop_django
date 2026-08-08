from django.urls import path
from .views import (
    BrandListCreate, BrandDetail, BrandNameSuggestions,
    CategoryListCreate, CategoryDetail, CategoryTree, CategoryStatusList, CategoryAssignDetails,
    CategoryNameSuggestions,
    CategoryDetailListCreate, CategoryDetailDetail, CategoryDetailNameSuggestions,
    ProductListCreate, ProductDetail,
    ProductFormOptions, ProductFilterOptions, ProductDetailDefinitions, ProductCompleteCreate,
    ProductCompleteUpdate,
    ProductFileDetail, ProductFileListCreate, ProductFileReorder,
    ProductDetailListCreate,
    ProductVariantListCreate, ProductVariantFormOptions, VariantDetail, VariantList,
    CategoryAssignVariantAttributes, VariantAttributeListCreate,
    VariantAttributeDetail, VariantOptionListCreate, VariantOptionDetail,
)
from .storefront import (
    StorefrontProductDetail,
    StorefrontProductQuickView,
    StorefrontProductSearch,
)
from .digikala_views import (
    DigikalaImportCreate,
    DigikalaJobCancel,
    DigikalaJobDetail,
    DigikalaJobList,
    DigikalaJobRetryFailures,
    DigikalaListingListCreate,
    DigikalaListingOptions,
    DigikalaListingProducts,
    DigikalaMappingCategoryOptions,
    DigikalaMappingDetail,
    DigikalaMappingListCreate,
)

urlpatterns = [
    # Digikala file-based import workflow
    path("digikala/listing-options", DigikalaListingOptions.as_view()),
    path("digikala/listings", DigikalaListingListCreate.as_view()),
    path(
        "digikala/listings/<uuid:listing_id>/products",
        DigikalaListingProducts.as_view(),
    ),
    path("digikala/import-jobs", DigikalaImportCreate.as_view()),
    path("digikala/jobs", DigikalaJobList.as_view()),
    path("digikala/jobs/<uuid:job_id>", DigikalaJobDetail.as_view()),
    path("digikala/jobs/<uuid:job_id>/cancel", DigikalaJobCancel.as_view()),
    path(
        "digikala/jobs/<uuid:job_id>/retry-failures",
        DigikalaJobRetryFailures.as_view(),
    ),
    path("digikala/mappings", DigikalaMappingListCreate.as_view()),
    path(
        "digikala/mappings/category-options",
        DigikalaMappingCategoryOptions.as_view(),
    ),
    path(
        "digikala/mappings/<int:category_id>",
        DigikalaMappingDetail.as_view(),
    ),
    path("storefront/products", StorefrontProductSearch.as_view()),
    path(
        "storefront/products/<str:slug>/quick-view",
        StorefrontProductQuickView.as_view(),
    ),
    path("storefront/products/<str:slug>", StorefrontProductDetail.as_view()),
    # Brands
    path("brands", BrandListCreate.as_view()),
    path("brands/name-suggestions", BrandNameSuggestions.as_view()),
    path("brands/<int:id>", BrandDetail.as_view()),
    # Categories
    path("categories", CategoryListCreate.as_view()),
    path("categories/tree", CategoryTree.as_view()),
    path("categories/name-suggestions", CategoryNameSuggestions.as_view()),
    path("category-statuses", CategoryStatusList.as_view()),
    path("categories/<int:id>", CategoryDetail.as_view()),
    path("categories/<int:id>/assign-details", CategoryAssignDetails.as_view()),
    path("categories/<int:id>/assign-variant-attributes", CategoryAssignVariantAttributes.as_view()),

    # Category Details (attributes)
    path("category-details", CategoryDetailListCreate.as_view()),
    path("category-details/name-suggestions", CategoryDetailNameSuggestions.as_view()),
    path("category-details/<int:id>", CategoryDetailDetail.as_view()),

    # Variant attributes and options
    path("variant-attributes", VariantAttributeListCreate.as_view()),
    path("variant-attributes/<int:id>", VariantAttributeDetail.as_view()),
    path("variant-options", VariantOptionListCreate.as_view()),
    path("variant-options/<int:id>", VariantOptionDetail.as_view()),

    # Products
    path("product-form-options", ProductFormOptions.as_view()),
    path("product-filter-options", ProductFilterOptions.as_view()),
    path("product-detail-definitions", ProductDetailDefinitions.as_view()),
    path("products/create", ProductCompleteCreate.as_view()),
    path("products/<int:id>/update", ProductCompleteUpdate.as_view()),
    path("products", ProductListCreate.as_view()),
    path("products/<int:id>", ProductDetail.as_view()),
    path("products/<int:product_id>/details", ProductDetailListCreate.as_view()),
    path("products/<int:product_id>/variants", ProductVariantListCreate.as_view()),
    path("products/<int:product_id>/variant-form-options", ProductVariantFormOptions.as_view()),
    path("products/<int:product_id>/files", ProductFileListCreate.as_view()),
    path(
        "products/<int:product_id>/files/reorder",
        ProductFileReorder.as_view(),
    ),
    path(
        "products/<int:product_id>/files/<int:relation_id>",
        ProductFileDetail.as_view(),
    ),

    # Variants (standalone)
    path("variants", VariantList.as_view()),
    path("variants/<int:id>", VariantDetail.as_view()),
]
