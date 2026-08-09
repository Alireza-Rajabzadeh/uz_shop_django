from django.contrib import admin

from .models import Wishlist


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "product", "created_at"]
    list_select_related = ["customer", "product"]
    search_fields = ["product__name", "customer__phone"]