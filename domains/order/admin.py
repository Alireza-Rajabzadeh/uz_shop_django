from django.contrib import admin

from .models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderPayment,
    OrderPaymentChannel,
    OrderPaymentChannelSupportMethod,
    OrderPaymentMethod,
    OrderStatus,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["variant", "sku", "quantity", "unit_price", "final_price"]


class OrderPaymentInline(admin.TabularInline):
    model = OrderPayment
    extra = 0


@admin.register(OrderStatus)
class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "fa_name"]


@admin.register(OrderPaymentMethod)
class OrderPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "fa_name", "available"]


@admin.register(OrderPaymentChannel)
class OrderPaymentChannelAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "fa_name", "account_number", "card_number", "owner_name"]


@admin.register(OrderPaymentChannelSupportMethod)
class OrderPaymentChannelSupportMethodAdmin(admin.ModelAdmin):
    list_display = ["payment_channel", "payment_method"]
    list_select_related = ["payment_channel", "payment_method"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "status", "total_amount", "reservation_expires_at", "created_at"]
    list_select_related = ["customer", "status"]
    search_fields = ["customer__phone"]
    inlines = [OrderItemInline, OrderPaymentInline]


@admin.register(OrderItemReservation)
class OrderItemReservationAdmin(admin.ModelAdmin):
    list_display = ["id", "order_item", "inventory_type", "inventory_id", "quantity"]


@admin.register(OrderPayment)
class OrderPaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "payment_method", "status", "amount", "ref_number", "created_at"]
    list_select_related = ["order", "payment_method"]