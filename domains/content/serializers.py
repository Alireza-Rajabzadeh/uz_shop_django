from rest_framework import serializers

from .models import LandingPage


class LandingPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandingPage
        fields = [
            "id",
            "title",
            "slug",
            "draft_content",
            "published_content",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
