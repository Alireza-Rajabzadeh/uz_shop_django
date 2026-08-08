from django.urls import path

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
]