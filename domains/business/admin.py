from django.contrib import admin

from .models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "availability_status", "cache_ttl", "updated_at")


@admin.register(BusinessPhone)
class BusinessPhoneAdmin(admin.ModelAdmin):
    list_display = ("title", "number", "visibility", "status", "position")
    list_filter = ("visibility", "status")
    search_fields = ("key", "title", "number")

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()


@admin.register(BusinessSocialLink)
class BusinessSocialLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "logo_file", "visibility", "status", "position")
    list_filter = ("platform", "visibility", "status")
    search_fields = ("key", "title", "url")

    def get_readonly_fields(self, request, obj=None):
        return ("key",) if obj else ()


@admin.register(BusinessWorkingDay)
class BusinessWorkingDayAdmin(admin.ModelAdmin):
    list_display = ("weekday", "is_open", "opens_at", "closes_at")
