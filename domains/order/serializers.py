import json

from rest_framework import serializers

from domains.files.services import FileService

from .models import OrderStatus, ReturnRequest, ReturnRequestEvidence, ReturnRequestItem


class ReturnRequestItemInputSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ReturnRequestCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(allow_blank=False)
    customer_note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    refund_destination_type = serializers.ChoiceField(
        choices=ReturnRequest.RefundDestinationType.choices
    )
    refund_destination_value = serializers.CharField(max_length=64, write_only=True)
    items = serializers.JSONField()
    images = serializers.ListField(
        child=serializers.FileField(), required=False, allow_empty=True, max_length=5
    )

    def validate_items(self, items):
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError("Must be valid JSON.") from exc
        serializer = ReturnRequestItemInputSerializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data
        if not items:
            raise serializers.ValidationError("This list may not be empty.")
        item_ids = [item["order_item_id"] for item in items]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError("Each order item may only appear once.")
        return items

    def validate_images(self, images):
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        errors = []
        for image in images:
            if image.content_type not in allowed_types:
                errors.append(f"{image.name}: only JPEG, PNG, and WebP are allowed.")
            elif image.size > 5 * 1024 * 1024:
                errors.append(f"{image.name}: image size must not exceed 5MB.")
        if errors:
            raise serializers.ValidationError(errors)
        return images


class ReturnRequestItemSerializer(serializers.ModelSerializer):
    order_item_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReturnRequestItem
        fields = ["id", "order_item_id", "quantity", "reason"]


class ReturnRequestEvidenceSerializer(serializers.ModelSerializer):
    file_id = serializers.UUIDField(read_only=True)
    original_name = serializers.CharField(source="file.original_name", read_only=True)
    content_type = serializers.CharField(source="file.content_type", read_only=True)
    size = serializers.IntegerField(source="file.size", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ReturnRequestEvidence
        fields = ["id", "file_id", "position", "original_name", "content_type", "size", "url"]

    def get_url(self, obj):
        try:
            return FileService().url(obj.file)
        except FileService.Error:
            return None


class ReturnRequestSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(read_only=True)
    items = ReturnRequestItemSerializer(many=True, read_only=True)
    evidence = ReturnRequestEvidenceSerializer(many=True, read_only=True)
    refund_destination_masked = serializers.SerializerMethodField()

    def get_refund_destination_masked(self, obj):
        return f"****{obj.refund_destination_value[-4:]}"

    class Meta:
        model = ReturnRequest
        fields = [
            "id",
            "order_id",
            "status",
            "reason",
            "customer_note",
            "refund_destination_type",
            "refund_destination_masked",
            "customer_response",
            "requested_at",
            "approved_at",
            "received_at",
            "completed_at",
            "created_at",
            "updated_at",
            "items",
            "evidence",
        ]


class AdminReturnActionSerializer(serializers.Serializer):
    admin_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_response = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class AdminOrderListQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True)
    in_progress = serializers.BooleanField(required=False, default=False)
    has_active_returns = serializers.BooleanField(required=False, default=False)
    search = serializers.CharField(required=False, allow_blank=True)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    state_id = serializers.IntegerField(required=False, min_value=1)
    city_id = serializers.IntegerField(required=False, min_value=1)
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
