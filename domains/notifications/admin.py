from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Provider, ProviderStatus, SentNotification


@admin.register(ProviderStatus)
class ProviderStatusAdmin(ModelAdmin):
    list_display = ["name", "code"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Provider)
class ProviderAdmin(ModelAdmin):
    list_display = ["name", "code", "service_type", "status", "is_default", "updated_at"]
    list_filter = ["service_type", "status", "is_default"]
    search_fields = ["name", "code"]
    readonly_fields = ["code", "service_type", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SentNotification)
class SentNotificationAdmin(ModelAdmin):
    list_display = ["receiver", "service_type", "provider_name", "status", "created_at"]
    list_filter = ["service_type", "status", "provider"]
    search_fields = ["receiver", "external_id"]
    exclude = ["message"]
    readonly_fields = [field.name for field in SentNotification._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
