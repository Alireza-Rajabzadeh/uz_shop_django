from django.contrib import admin

from .models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderHistory,
    OrderStatus,
    OrderAction,
    OrderStatusAction,
)
from domains.payments.models import Payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["variant", "sku", "quantity", "unit_price", "final_price"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = [
        "payment_method", "payment_channel", "amount", "status", "ref_number",
        "resource_account_number", "extra_data", "created_at", "updated_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderStatus)
class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "fa_name"]
    search_fields = ["name", "fa_name", "description"]


@admin.register(OrderAction)
class OrderActionAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "name", "fa_name", "admin", "customer", "set_status"]
    list_filter = ["admin", "customer"]
    search_fields = ["code", "name", "fa_name"]


@admin.register(OrderStatusAction)
class OrderStatusActionAdmin(admin.ModelAdmin):
    list_display = ["id", "order_status", "order_action"]
    list_select_related = ["order_status", "order_action"]


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "action", "user_id", "user_model", "description", "created_at"]
    list_select_related = ["order", "action"]
    readonly_fields = [
        "order",
        "action",
        "user_id",
        "user_model",
        "before_values",
        "after_values",
        "description",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "status", "total_amount", "reservation_expires_at", "created_at"]
    list_select_related = ["customer", "status"]
    search_fields = ["customer__phone"]
    inlines = [OrderItemInline, PaymentInline]


@admin.register(OrderItemReservation)
class OrderItemReservationAdmin(admin.ModelAdmin):
    list_display = ["id", "order_item", "inventory_type", "inventory_id", "quantity"]
