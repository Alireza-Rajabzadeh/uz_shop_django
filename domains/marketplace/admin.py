from django.contrib import admin

from .models import BusinessOffer, OfferPriceHistory


@admin.register(BusinessOffer)
class BusinessOfferAdmin(admin.ModelAdmin):
    list_display = ["business", "variant", "price", "discount_type", "discount_value", "is_active", "created_at"]
    list_filter = ["is_active", "discount_type"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(OfferPriceHistory)
class OfferPriceHistoryAdmin(admin.ModelAdmin):
    """Append-only audit trail. Never editable, never deletable from the UI."""

    list_display = [
        "variant",
        "old_price",
        "new_price",
        "old_discount_type",
        "new_discount_type",
        "source",
        "created_at",
    ]
    list_filter = ["source", "new_discount_type"]
    search_fields = ["variant__sku"]
    autocomplete_fields = ["variant", "offer"]
    readonly_fields = [f.name for f in OfferPriceHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
