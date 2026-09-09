from django.contrib import admin
from .models import VendorStatus, Vendor, VendorPreference


@admin.register(VendorStatus)
class VendorStatusAdmin(admin.ModelAdmin):
    list_display = ("title", "name", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("vendor_code", "first_name", "last_name", "phone", "email", "national_id", "status", "is_active")
    list_filter = ("status", "gender")
    search_fields = ("vendor_code", "phone", "first_name", "last_name", "email", "national_id")
    readonly_fields = ("vendor_code", "created_at", "updated_at")

    def is_active(self, obj):
        return obj.status.is_active
    is_active.boolean = True


@admin.register(VendorPreference)
class VendorPreferenceAdmin(admin.ModelAdmin):
    list_display = ("vendor", "receive_order_emails", "receive_sms_notifications", "receive_push_notifications")
