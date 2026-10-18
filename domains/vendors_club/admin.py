from django.contrib import admin

from .models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
    VendorClubPointTransactionType,
)


@admin.register(VendorClubActivity)
class VendorClubActivityAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "points", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    # `code` is the stable identifier other code keys off, so it is created
    # once and never edited. Making it read-only here keeps the model's
    # immutability guard from ever surfacing as an error on save.
    readonly_fields = ["code", "created_at", "updated_at"]
    ordering = ["id"]


@admin.register(VendorClubPointTransactionType)
class VendorClubPointTransactionTypeAdmin(admin.ModelAdmin):
    """Reference vocabulary for the ledger. Seeded once, never hand-edited."""

    list_display = ["code", "name"]
    search_fields = ["code", "name"]
    readonly_fields = ["code", "name", "description"]
    ordering = ["id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VendorClubMembership)
class VendorClubMembershipAdmin(admin.ModelAdmin):
    list_display = [
        "vendor",
        "lifetime_points",
        "available_points",
        "last_synced_at",
        "updated_at",
    ]
    search_fields = ["vendor__vendor_code", "vendor__phone"]
    # Balances are a cache of the ledger, so they are never hand-edited here.
    readonly_fields = [
        "vendor",
        "lifetime_points",
        "available_points",
        "last_synced_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["id"]


@admin.register(VendorClubPointTransaction)
class VendorClubPointTransactionAdmin(admin.ModelAdmin):
    """Append-only ledger. Never editable, never deletable from the UI."""

    list_display = [
        "membership",
        "transaction_type",
        "points",
        "activity",
        "reference_type",
        "reference_id",
        "created_at",
    ]
    list_filter = ["transaction_type", "activity"]
    search_fields = ["membership__vendor__vendor_code", "reference_id"]
    readonly_fields = [field.name for field in VendorClubPointTransaction._meta.fields]
    ordering = ["-created_at", "-id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
