import uuid

from django.conf import settings
from django.db import models


class FileStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "files_file_status"
        ordering = ["name"]

    def __str__(self):
        return self.name


class File(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.ForeignKey(
        FileStatus,
        on_delete=models.PROTECT,
        related_name="files",
    )
    storage_alias = models.CharField(max_length=50, default="default")
    object_key = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    content_type = models.CharField(max_length=255, blank=True)
    extension = models.CharField(max_length=50, blank=True)
    size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "files_file"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["storage_alias", "object_key"],
                name="files_unique_storage_object",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="files_status_created_idx"),
            models.Index(fields=["file_type", "created_at"], name="files_type_created_idx"),
            models.Index(fields=["checksum"], name="files_checksum_idx"),
        ]

    def __str__(self):
        return self.original_name
