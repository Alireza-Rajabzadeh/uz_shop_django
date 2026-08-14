from rest_framework import serializers

from domains.files.models import File

from .models import PaymentChannel, PaymentMethod
from .online_payment_providers import provider_availability


class ConfirmPaymentSerializer(serializers.Serializer):
    payment_method = serializers.CharField(max_length=50)
    payment_channel_id = serializers.IntegerField(min_value=1)
    ref_number = serializers.CharField(required=False, allow_blank=True, max_length=128, default="")
    resource_account_number = serializers.CharField(
        required=False, allow_blank=True, max_length=64, default=""
    )
    documents = serializers.ListField(
        child=serializers.FileField(), required=False, allow_empty=True
    )

    def validate_payment_method(self, value):
        return value.strip().casefold()

    def validate_documents(self, value):
        allowed = {"image/jpeg", "image/png", "image/webp"}
        for document in value:
            if getattr(document, "content_type", "") not in allowed:
                raise serializers.ValidationError("Only JPEG, PNG, and WebP images are allowed.")
        return value


class ListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=150)
    is_active = serializers.ChoiceField(required=False, choices=["true", "false"])
    page = serializers.IntegerField(required=False, min_value=1)
    ordering = serializers.CharField(required=False, allow_blank=True, max_length=50)
    channel_code = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate_is_active(self, value):
        return value == "true"


class ChannelListQuerySerializer(ListQuerySerializer):
    supported_method = serializers.IntegerField(required=False, min_value=1)


class PaymentMethodReadSerializer(serializers.ModelSerializer):
    icon = serializers.SerializerMethodField()
    supported_channel_count = serializers.IntegerField(read_only=True, default=0)
    provider_available = serializers.SerializerMethodField()
    provider_unavailable_reason = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = [
            "id", "code", "name", "fa_name", "icon", "point_to_channel_field",
            "requires_documents", "is_active",
            "supported_channel_count", "provider_available",
            "provider_unavailable_reason",
        ]

    def get_icon(self, obj):
        from .services import PaymentService

        return PaymentService.file_payload(obj.icon_file)

    def get_provider_available(self, obj):
        if obj.code != "online":
            return True
        channel_code = self.context.get("channel_code")
        return bool(channel_code and provider_availability(channel_code)[0])

    def get_provider_unavailable_reason(self, obj):
        if obj.code == "online":
            channel_code = self.context.get("channel_code")
            if channel_code:
                return provider_availability(channel_code)[1]
            return "Select a channel with an implemented online payment provider."
        return None


class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    icon_file_id = serializers.PrimaryKeyRelatedField(
        source="icon_file", queryset=File.objects.select_related("status"),
        required=False, allow_null=True,
    )

    class Meta:
        model = PaymentMethod
        fields = [
            "name", "fa_name", "icon_file_id", "point_to_channel_field",
            "requires_documents", "is_active",
        ]

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "This field is immutable." for key in unknown})
        return super().to_internal_value(data)


class PaymentChannelWriteSerializer(serializers.ModelSerializer):
    logo_file_id = serializers.PrimaryKeyRelatedField(
        source="logo_file", queryset=File.objects.select_related("status"),
        required=False, allow_null=True,
    )
    payment_method_ids = serializers.PrimaryKeyRelatedField(
        source="supported_methods_value",
        queryset=PaymentMethod.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = PaymentChannel
        fields = [
            "code", "name", "fa_name", "account_number", "card_number", "owner_name",
            "extra_data", "is_active", "logo_file_id", "payment_method_ids",
        ]
        extra_kwargs = {
            "code": {"required": True},
            "payment_method_ids": {"required": False},
        }

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in unknown})
        if self.instance is not None and "code" in data:
            raise serializers.ValidationError({"code": "This field is immutable."})
        return super().to_internal_value(data)

    def validate_payment_method_ids(self, value):
        ids = [method.id for method in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Payment method IDs must be unique.")
        return value
