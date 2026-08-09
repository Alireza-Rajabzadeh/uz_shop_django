from rest_framework import serializers


class AdminCartListQuerySerializer(serializers.Serializer):
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


class CartItemAddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(required=False, default=1, min_value=1)


class CartItemQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)