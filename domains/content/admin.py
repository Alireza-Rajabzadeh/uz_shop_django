from django.contrib import admin

from .models import LandingPage, SEORecord


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "slug", "status", "published_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SEORecord)
class SEORecordAdmin(admin.ModelAdmin):
    list_display = [
        "id", "resource_type", "resource_id", "title", "index", "follow",
        "updated_at",
    ]
    list_filter = ["resource_type", "index", "follow"]
    search_fields = ["resource_type", "title", "description"]
    readonly_fields = ["created_at", "updated_at"]
