from django.contrib import admin

from .models import Feature, Package, PackageFeature, PackagePriceHistory


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "price", "off_discount", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    # `code` is the stable identifier other code keys off, so it is created
    # once and never edited. Making it read-only here keeps the model's
    # immutability guard from ever surfacing as an error on save.
    readonly_fields = ["code", "created_at", "updated_at"]
    ordering = ["id"]


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "created_at"]
    search_fields = ["code", "name"]
    readonly_fields = ["code", "created_at", "updated_at"]
    ordering = ["id"]


@admin.register(PackageFeature)
class PackageFeatureAdmin(admin.ModelAdmin):
    list_display = ["package", "feature", "updated_at"]
    list_filter = ["package", "feature"]
    search_fields = ["package__code", "feature__code"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["id"]


@admin.register(PackagePriceHistory)
class PackagePriceHistoryAdmin(admin.ModelAdmin):
    """Append-only audit trail. Never editable, never deletable from the UI.

    Written by `domains.packages.signals`, so there is no form here that
    could write a row the model layer did not sanction.
    """

    list_display = ["package", "price", "off_discount", "created_at"]
    list_filter = ["package"]
    search_fields = ["package__code"]
    readonly_fields = [f.name for f in PackagePriceHistory._meta.fields]
    ordering = ["created_at", "id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request):
        return False
