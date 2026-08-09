from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "created_at", "updated_at"]
    inlines = [CartItemInline]
    search_fields = ["customer__phone"]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["id", "cart", "variant", "quantity", "created_at"]
    list_select_related = ["cart", "variant"]