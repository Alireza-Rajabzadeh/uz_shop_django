from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from domains.inventory.services import InventoryCostService

from .models import (
    InventoryStrategy,
    InventorySupply,
    InventorySupplyCost,
    SerializedStock,
    SerializedStockStatus,
    VariantPriceHistory,
    VariantPricing,
    Warehouse,
    WarehouseStatus,
    WarehouseStock,
)

inventory_cost_service = InventoryCostService()


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
    list_display = ["serial_number", "variant", "warehouse", "status", "sellable", "reserved", "supply"]
    list_filter = ["status", "warehouse", "sellable", "reserved"]
    search_fields = ["serial_number", "variant__sku"]
    autocomplete_fields = ["variant", "warehouse", "status", "supply"]


class InventorySupplyCostInline(TabularInline):
    model = InventorySupplyCost
    extra = 0
    fields = ["type", "amount", "description"]
    autocomplete_fields = []


@admin.register(InventorySupply)
class InventorySupplyAdmin(ModelAdmin):
    list_display = [
        "variant",
        "warehouse",
        "quantity",
        "remaining_quantity",
        "unit_buy_price",
        "base_cost_display",
        "extra_cost_display",
        "landed_cost_total_display",
        "landed_unit_cost_display",
        "supplied_at",
        "is_received_display",
        "received_at",
        "reference_number",
        "invoice_number",
    ]
    list_filter = ["warehouse", "supplied_at"]
    search_fields = ["variant__sku", "reference_number", "invoice_number"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["variant", "warehouse"]
    inlines = [InventorySupplyCostInline]

    @admin.display(description="Received", boolean=True)
    def is_received_display(self, obj):
        return obj.is_received

    @admin.display(description="Base cost", ordering="unit_buy_price")
    def base_cost_display(self, obj):
        return inventory_cost_service.get_base_cost_total(obj)

    @admin.display(description="Extra costs")
    def extra_cost_display(self, obj):
        return inventory_cost_service.get_extra_cost_total(obj)

    @admin.display(description="Landed total")
    def landed_cost_total_display(self, obj):
        return inventory_cost_service.get_landed_cost_total(obj)

    @admin.display(description="Landed unit cost")
    def landed_unit_cost_display(self, obj):
        return inventory_cost_service.get_landed_unit_cost(obj)


@admin.register(VariantPricing)
class VariantPricingAdmin(ModelAdmin):
    list_display = ["variant", "expected_profit_percentage", "cost_strategy", "updated_at"]
    list_filter = ["cost_strategy"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant"]


@admin.register(VariantPriceHistory)
class VariantPriceHistoryAdmin(ModelAdmin):
    list_display = [
        "variant",
        "old_price",
        "new_price",
        "cost_basis",
        "cost_strategy",
        "source",
        "created_at",
    ]
    list_filter = ["cost_strategy", "source"]
    search_fields = ["variant__sku", "variant__product__name"]
    autocomplete_fields = ["variant"]
    readonly_fields = ["created_at"]


@admin.register(InventorySupplyCost)
class InventorySupplyCostAdmin(ModelAdmin):
    list_display = ["supply_variant_sku", "type", "amount", "description", "created_at"]
    list_filter = ["type", "supply__warehouse"]
    search_fields = [
        "supply__variant__sku",
        "supply__reference_number",
        "supply__invoice_number",
        "description",
    ]

    @admin.display(description="Variant SKU", ordering="supply__variant__sku")
    def supply_variant_sku(self, obj):
        return obj.supply.variant.sku
