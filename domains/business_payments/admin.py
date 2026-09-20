from django.contrib import admin

from .models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentChannelSupportedMethod,
    BusinessPaymentDocument,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)


@admin.register(BusinessPaymentStatus)
class BusinessPaymentStatusAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "title", "is_active", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(BusinessPaymentMethod)
class BusinessPaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "business",
        "code",
        "name",
        "fa_name",
        "point_to_channel_field",
        "requires_documents",
        "is_active",
    ]
    list_select_related = ["business"]
    readonly_fields = ["code"]


@admin.register(BusinessPaymentChannel)
class BusinessPaymentChannelAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "business",
        "code",
        "name",
        "fa_name",
        "is_active",
    ]
    list_select_related = ["business"]
    readonly_fields = ["created_at", "updated_at"]

    def get_readonly_fields(self, request, obj=None):
        return [*self.readonly_fields, "code"] if obj else self.readonly_fields


@admin.register(BusinessPaymentChannelSupportedMethod)
class BusinessPaymentChannelSupportedMethodAdmin(admin.ModelAdmin):
    list_display = ["payment_channel", "payment_method"]
    list_select_related = ["payment_channel", "payment_method"]


@admin.register(BusinessPayment)
class BusinessPaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "business",
        "order",
        "payment_method",
        "status",
        "amount",
        "created_at",
    ]
    list_select_related = ["business", "order", "payment_method"]
    readonly_fields = [
        "business",
        "order",
        "payment_method",
        "payment_channel",
        "amount",
        "status",
        "ref_number",
        "resource_account_number",
        "extra_data",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BusinessPaymentDocument)
class BusinessPaymentDocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "payment", "file", "created_at"]
    list_select_related = ["payment", "file"]
    readonly_fields = ["payment", "file", "created_at"]
