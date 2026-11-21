from rest_framework import serializers

from ..models.seo_record import SEORecord


class SEORecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SEORecord
        fields = [
            "id",
            "resource_type",
            "resource_id",
            "title",
            "description",
            "canonical_url",
            "image_id",
            "index",
            "follow",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "resource_type",
            "resource_id",
            "created_at",
            "updated_at",
        ]
