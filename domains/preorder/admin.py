from django.contrib import admin

from .models import PreOrder


@admin.register(PreOrder)
class PreOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "product", "created_at"]
    list_select_related = ["customer", "product"]
    search_fields = ["product__name", "customer__phone"]