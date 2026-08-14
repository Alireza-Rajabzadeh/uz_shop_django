from rest_framework import serializers

from .models import OrderStatus


class AdminOrderListQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True)
    search = serializers.CharField(required=False, allow_blank=True)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    ordering = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if (
            attrs.get("created_from") is not None
            and attrs.get("created_to") is not None
            and attrs["created_from"] > attrs["created_to"]
        ):
            raise serializers.ValidationError(
                {"created_to": "Must be on or after the start date."}
            )
        return attrs


class AdminOrderStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatus
        fields = [
            "id",
            "name",
            "fa_name",
            "description",
        ]
