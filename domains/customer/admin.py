from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("phone", "first_name", "last_name", "email", "is_active", "created_at")
    search_fields = ("phone", "first_name", "last_name", "email")
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")
