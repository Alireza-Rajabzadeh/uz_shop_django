from django.contrib import admin

from .models import BusinessCategory, BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay, SocialMedia, SocialMediaIcon


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
