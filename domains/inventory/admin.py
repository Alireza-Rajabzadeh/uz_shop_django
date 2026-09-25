from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from domains.inventory.services import InventoryCostService

from .models import (
    Inventory,
    InventoryAttributeDefinition,
    InventorySupply,
    InventorySupplyCost,
    InventoryTransfer,
    InventoryUnit,
    InventoryUnitAttribute,
    VariantPriceHistory,
    Warehouse,
    WarehouseStatus,
)

inventory_cost_service = InventoryCostService()


@admin.register(Inventory)
class InventoryAdmin(ModelAdmin):
    list_display = ["variant", "warehouse", "business", "quantity", "sellable", "reserved", "available", "min_stock"]
    list_filter = ["warehouse", "business"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant", "warehouse", "business"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(InventoryUnit)
class InventoryUnitAdmin(ModelAdmin):
    list_display = ["pk", "inventory", "state", "supply", "created_at", "updated_at"]
    list_filter = ["state"]
    search_fields = ["inventory__variant__sku", "inventory__warehouse__code"]
    autocomplete_fields = ["inventory", "supply"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(InventoryAttributeDefinition)
class InventoryAttributeDefinitionAdmin(ModelAdmin):
    list_display = ["name", "code", "business", "type", "created_at"]
    list_filter = ["type", "business"]
    search_fields = ["name", "code"]
    autocomplete_fields = ["business"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(InventoryUnitAttribute)
class InventoryUnitAttributeAdmin(ModelAdmin):
    list_display = ["inventory_unit", "attribute_definition", "value"]
    search_fields = [
        "inventory_unit__inventory__variant__sku",
        "attribute_definition__name",
        "value",
    ]
    autocomplete_fields = ["inventory_unit", "attribute_definition"]


@admin.register(InventoryTransfer)
class InventoryTransferAdmin(ModelAdmin):
    list_display = [
        "variant",
        "source_inventory",
        "destination_inventory",
        "quantity",
        "unit_count",
        "created_at",
    ]
    search_fields = ["variant__sku", "notes"]
    autocomplete_fields = ["source_inventory", "destination_inventory", "variant"]
    readonly_fields = ["created_at"]


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
