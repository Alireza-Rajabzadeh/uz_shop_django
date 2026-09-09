from django.contrib import admin

from .models import BusinessOffer


@admin.register(BusinessOffer)
class BusinessOfferAdmin(admin.ModelAdmin):
    list_display = ["business", "variant", "price", "discount_type", "discount_value", "is_active", "created_at"]
    list_filter = ["is_active", "discount_type"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant"]
    readonly_fields = ["created_at", "updated_at"]
