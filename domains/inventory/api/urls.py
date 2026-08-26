from django.urls import path

from .views import (
    InventoryReportSupplyListView,
    InventoryReportSummaryView,
    InventoryReportVariantListView,
    InventoryStrategyOptions,
    InventoryVariantList,
    PricingListView,
    PricingStrategyOptions,
    SerializedStatusOptions,
    SupplyCostTypeOptions,
    SupplyDetail,
    SupplyListCreate,
    SupplyReceive,
    VariantInventoryDetail,
    VariantPricingApplyView,
    VariantPricingHistoryView,
    VariantPricingView,
    WarehouseDetail,
    WarehouseListCreate,
    WarehouseStatusOptions,
)


urlpatterns = [
    path("variants", InventoryVariantList.as_view()),
    path("variants/<int:variant_id>", VariantInventoryDetail.as_view()),
    path("variants/<int:variant_id>/pricing", VariantPricingView.as_view()),
    path(
        "variants/<int:variant_id>/pricing/apply",
        VariantPricingApplyView.as_view(),
    ),
    path(
        "variants/<int:variant_id>/pricing/history",
        VariantPricingHistoryView.as_view(),
    ),
    path("warehouses", WarehouseListCreate.as_view()),
    path("warehouses/<int:warehouse_id>", WarehouseDetail.as_view()),
    path("warehouse-statuses", WarehouseStatusOptions.as_view()),
    path("strategies", InventoryStrategyOptions.as_view()),
    path("serialized-statuses", SerializedStatusOptions.as_view()),
    path("supplies", SupplyListCreate.as_view()),
    path("supplies/<int:supply_id>", SupplyDetail.as_view()),
    path("supplies/<int:supply_id>/receive", SupplyReceive.as_view()),
    path("supply-cost-types", SupplyCostTypeOptions.as_view()),
    path("pricing", PricingListView.as_view()),
    path("pricing-strategies", PricingStrategyOptions.as_view()),
    path("reports/summary", InventoryReportSummaryView.as_view()),
    path("reports/variants", InventoryReportVariantListView.as_view()),
    path("reports/supplies", InventoryReportSupplyListView.as_view()),
]
