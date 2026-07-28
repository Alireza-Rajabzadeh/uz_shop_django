from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    InventoryStrategy,
    SerializedStock,
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)


@admin.register(InventoryStrategy)
class InventoryStrategyAdmin(ModelAdmin):
    list_display = ["code", "name"]
    search_fields = ["code", "name"]


@admin.register(WarehouseStatus)
class WarehouseStatusAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Warehouse)
class WarehouseAdmin(ModelAdmin):
    list_display = ["code", "name", "city", "status", "is_default"]
    list_filter = ["status", "is_default"]
    search_fields = ["code", "name"]
    raw_id_fields = ["city"]
    autocomplete_fields = ["status"]


@admin.register(WarehouseStock)
class WarehouseStockAdmin(ModelAdmin):
    list_display = ["variant", "warehouse", "quantity", "sellable", "reserved", "available"]
    list_filter = ["warehouse"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant", "warehouse"]


@admin.register(SerializedStockStatus)
class SerializedStockStatusAdmin(ModelAdmin):
    list_display = ["code", "name"]
    search_fields = ["code", "name"]


@admin.register(SerializedStock)
class SerializedStockAdmin(ModelAdmin):
    list_display = ["serial_number", "variant", "warehouse", "status", "sellable", "reserved"]
    list_filter = ["status", "warehouse", "sellable", "reserved"]
    search_fields = ["serial_number", "variant__sku"]
    autocomplete_fields = ["variant", "warehouse", "status"]
