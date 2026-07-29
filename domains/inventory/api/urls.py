from django.urls import path

from .views import (
    InventoryStrategyOptions,
    InventoryVariantList,
    SerializedStatusOptions,
    VariantInventoryDetail,
    WarehouseDetail,
    WarehouseListCreate,
    WarehouseStatusOptions,
)


urlpatterns = [
    path("variants", InventoryVariantList.as_view()),
    path("variants/<int:variant_id>", VariantInventoryDetail.as_view()),
    path("warehouses", WarehouseListCreate.as_view()),
    path("warehouses/<int:warehouse_id>", WarehouseDetail.as_view()),
    path("warehouse-statuses", WarehouseStatusOptions.as_view()),
    path("strategies", InventoryStrategyOptions.as_view()),
    path("serialized-statuses", SerializedStatusOptions.as_view()),
]
