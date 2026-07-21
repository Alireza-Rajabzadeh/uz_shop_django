from django.contrib import admin
from .models import CustomerStatus, Customer, CustomerAddress, CustomerPreference


@admin.register(CustomerStatus)
class CustomerStatusAdmin(admin.ModelAdmin):
    list_display = ("title", "name", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_code", "first_name", "last_name", "phone", "email", "status", "is_active")
    list_filter = ("status", "gender")
    search_fields = ("customer_code", "phone", "first_name", "last_name", "email")
    readonly_fields = ("customer_code", "created_at", "updated_at")

    def is_active(self, obj):
        return obj.status.is_active
    is_active.boolean = True


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ("customer", "title", "city", "is_default")
    list_filter = ("is_default",)


@admin.register(CustomerPreference)
class CustomerPreferenceAdmin(admin.ModelAdmin):
    list_display = ("customer", "receive_order_emails", "receive_sms_notifications", "receive_push_notifications")
