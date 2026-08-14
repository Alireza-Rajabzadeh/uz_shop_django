from django.contrib import admin

from .models import (
    Payment, PaymentChannel, PaymentChannelSupportedMethod, PaymentDocument,
    PaymentMethod,
)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        "id", "code", "name", "fa_name", "point_to_channel_field",
        "requires_documents", "is_active",
    ]
    readonly_fields = ["code"]


@admin.register(PaymentChannel)
class PaymentChannelAdmin(admin.ModelAdmin):
    list_display = ["id", "code", "name", "fa_name", "is_active"]
    readonly_fields = ["created_at", "updated_at"]

    def get_readonly_fields(self, request, obj=None):
        return [*self.readonly_fields, "code"] if obj else self.readonly_fields


@admin.register(PaymentChannelSupportedMethod)
class PaymentChannelSupportedMethodAdmin(admin.ModelAdmin):
    list_display = ["payment_channel", "payment_method"]
    list_select_related = ["payment_channel", "payment_method"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "payment_method", "status", "amount", "created_at"]
    list_select_related = ["order", "payment_method"]
    readonly_fields = [
        "order", "payment_method", "payment_channel", "amount", "status",
        "ref_number", "resource_account_number", "extra_data", "created_at", "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentDocument)
class PaymentDocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "payment", "file", "created_at"]
    readonly_fields = ["payment", "file", "created_at"]
