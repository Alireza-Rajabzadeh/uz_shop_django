from django.urls import path
from .views import (
    CategoryListCreate, CategoryDetail, CategoryTree, CategoryStatusList, CategoryAssignDetails,
    CategoryNameSuggestions,
    CategoryDetailListCreate, CategoryDetailDetail, CategoryDetailNameSuggestions,
    ProductListCreate, ProductDetail,
    ProductDetailListCreate,
    ProductVariantListCreate, VariantDetail, VariantList,
)

urlpatterns = [
    # Categories
    path("categories", CategoryListCreate.as_view()),
    path("categories/tree", CategoryTree.as_view()),
    path("categories/name-suggestions", CategoryNameSuggestions.as_view()),
    path("category-statuses", CategoryStatusList.as_view()),
    path("categories/<int:id>", CategoryDetail.as_view()),
    path("categories/<int:id>/assign-details", CategoryAssignDetails.as_view()),

    # Category Details (attributes)
    path("category-details", CategoryDetailListCreate.as_view()),
    path("category-details/name-suggestions", CategoryDetailNameSuggestions.as_view()),
    path("category-details/<int:id>", CategoryDetailDetail.as_view()),

    # Products
    path("products", ProductListCreate.as_view()),
    path("products/<int:id>", ProductDetail.as_view()),
    path("products/<int:product_id>/details", ProductDetailListCreate.as_view()),
    path("products/<int:product_id>/variants", ProductVariantListCreate.as_view()),

    # Variants (standalone)
    path("variants", VariantList.as_view()),
    path("variants/<int:id>", VariantDetail.as_view()),
]
