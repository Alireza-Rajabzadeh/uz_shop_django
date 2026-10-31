from django.contrib import admin

from .models import BusinessCategory, BusinessCharge, BusinessPhone, BusinessProfile, BusinessServiceMode, BusinessShipment, BusinessSocialLink, BusinessWorkingDay, SocialMedia, SocialMediaIcon


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "availability_status", "cache_ttl", "updated_at")
    search_fields = ("business_name", "display_name")


@admin.register(BusinessPhone)
class BusinessPhoneAdmin(admin.ModelAdmin):
    list_display = ("title", "number", "visibility", "status", "position")
    list_filter = ("visibility", "status")
    search_fields = ("key", "title", "number")

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()


@admin.register(BusinessSocialLink)
class BusinessSocialLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "social_media", "visibility", "status", "position")
    list_filter = ("visibility", "status")
    search_fields = ("key", "title", "url")

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()


@admin.register(SocialMedia)
class SocialMediaAdmin(admin.ModelAdmin):
    list_display = ("name", "fa_name", "slug", "is_active", "position")
    list_filter = ("is_active",)
    search_fields = ("name", "fa_name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SocialMediaIcon)
class SocialMediaIconAdmin(admin.ModelAdmin):
    list_display = ("social_media", "label", "file", "position")
    list_filter = ("social_media",)
    search_fields = ("label",)


@admin.register(BusinessWorkingDay)
class BusinessWorkingDayAdmin(admin.ModelAdmin):
    list_display = ("weekday", "is_open", "opens_at", "closes_at")


@admin.register(BusinessCategory)
class BusinessCategoryAdmin(admin.ModelAdmin):
    list_display = ("business", "category", "created_at")
    list_filter = ("business",)
    search_fields = ("business__display_name", "category__name")


@admin.register(BusinessShipment)
class BusinessShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "shipment_method",
        "pricing_method",
        "cost",
        "is_default",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_default", "is_active", "shipment_method", "pricing_method")
    search_fields = (
        "business__business_name",
        "business__display_name",
        "shipment_method__code",
        "pricing_method__code",
    )


@admin.register(BusinessCharge)
class BusinessChargeAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "name",
        "type",
        "calculation_type",
        "amount",
        "is_active",
        "is_mandatory",
        "updated_at",
    )
    list_filter = ("type", "calculation_type", "is_active", "is_mandatory")
    search_fields = ("business__business_name", "business__display_name", "name")


@admin.register(BusinessServiceMode)
class BusinessServiceModeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    # `code` is the stable identifier other code keys off, so it is created
    # once and never edited. Making it read-only here keeps the model's
    # immutability guard from ever surfacing as an error on save.
    readonly_fields = ("code", "created_at", "updated_at")
    ordering = ("id",)
