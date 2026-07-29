from django.conf import settings
from rest_framework import serializers

from domains.files.models import File, FileStatus
from domains.files.services import FileService


class FileStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileStatus
        fields = ["id", "name"]


class FileReadSerializer(serializers.ModelSerializer):
    status = FileStatusSerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id", "status", "storage_alias", "object_key", "original_name",
            "file_type", "content_type", "extension", "size", "checksum",
            "metadata", "created_by", "created_at", "updated_at", "deleted_at", "url",
        ]

    def get_url(self, obj):
        try:
            return FileService().url(obj)
        except FileService.Error:
            return None


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    storage_alias = serializers.CharField(max_length=50, default="default")
    metadata = serializers.JSONField(default=dict)

    def validate_file(self, value):
        if value.size > settings.FILE_MAX_UPLOAD_SIZE:
            raise serializers.ValidationError("File size cannot exceed 20 MB.")
        return value

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")
        return value


class FileMetadataSerializer(serializers.Serializer):
    metadata = serializers.JSONField()

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "This field is not mutable." for key in unknown})
        return super().to_internal_value(data)

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")
        return value


class FileListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.CharField(required=False, max_length=50)
    file_type = serializers.ChoiceField(
        required=False, choices=["image", "video", "document", "other"]
    )
    storage_alias = serializers.CharField(required=False, max_length=50)
    ordering = serializers.ChoiceField(
        required=False,
        default="-created_at",
        choices=[
            "created_at", "-created_at", "updated_at", "-updated_at",
            "original_name", "-original_name", "size", "-size",
            "file_type", "-file_type", "status__name", "-status__name",
        ],
    )
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class FileOrphanQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=255)
    file_type = serializers.ChoiceField(
        required=False, choices=["image", "video", "document", "other"]
    )
    storage_alias = serializers.CharField(required=False, max_length=50)
    ordering = FileListQuerySerializer().fields["ordering"]
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)
