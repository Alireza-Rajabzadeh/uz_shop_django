from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import File, FileStatus


@admin.register(FileStatus)
class FileStatusAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(File)
class FileAdmin(ModelAdmin):
    list_display = ["original_name", "file_type", "status", "size", "storage_alias", "created_at"]
    list_filter = ["status", "file_type", "storage_alias"]
    search_fields = ["original_name", "object_key", "checksum"]
    readonly_fields = [
        "id", "status", "storage_alias", "object_key", "original_name", "file_type",
        "content_type", "extension", "size", "checksum", "created_by", "created_at",
        "updated_at", "deleted_at",
    ]
