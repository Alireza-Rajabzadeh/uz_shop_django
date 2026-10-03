from django.contrib import admin

from .models import LandingPage, Page, SEORecord, SuggestionPage


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "slug", "business", "status", "published_at", "updated_at"]
    list_filter = ["status", "business"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "slug", "business", "status", "published_at", "updated_at"]
    list_filter = ["status", "business"]
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


@admin.register(SuggestionPage)
class SuggestionPageAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "slug", "required", "activate", "updated_at"]
    list_filter = ["required", "activate"]
    search_fields = ["title", "slug", "descriptions"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["created_at", "updated_at"]
