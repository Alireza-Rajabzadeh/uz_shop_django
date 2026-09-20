from rest_framework import serializers

from .models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)


class ListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.ChoiceField(
        choices=["true", "false"], required=False, allow_blank=True, default=""
    )
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    ordering = serializers.CharField(required=False, allow_blank=True, default="id")

    def to_internal_value(self, data):
        result = super().to_internal_value(data)
        if result["is_active"] == "true":
            result["is_active"] = True
        elif result["is_active"] == "false":
            result["is_active"] = False
        else:
            result["is_active"] = None
        return result


class ChannelListQuerySerializer(ListQuerySerializer):
    supported_method = serializers.IntegerField(required=False, min_value=1)


class PaymentListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    ordering = serializers.CharField(
        required=False, allow_blank=True, default="-created_at"
    )

    def validate_status(self, value):
        if not value:
            return ""
        if not BusinessPaymentStatus.objects.filter(
            name=value, is_active=True
        ).exists():
            raise serializers.ValidationError("Invalid payment status.")
        return value


class BusinessPaymentMethodReadSerializer(serializers.ModelSerializer):
    icon = serializers.SerializerMethodField()
    supported_channel_count = serializers.IntegerField(read_only=True, default=0)
    provider_available = serializers.SerializerMethodField()
    provider_unavailable_reason = serializers.SerializerMethodField()

    class Meta:
        model = BusinessPaymentMethod
        fields = [
            "id",
            "code",
            "name",
            "fa_name",
            "icon",
            "point_to_channel_field",
            "requires_documents",
            "is_active",
            "supported_channel_count",
            "provider_available",
            "provider_unavailable_reason",
        ]

    def get_icon(self, obj):
        from .services import BusinessPaymentService

        return BusinessPaymentService.file_payload(obj.icon_file)

    def get_provider_available(self, obj):
        if obj.code != "online":
            return True
        channel_code = self.context.get("channel_code", "")
        if not channel_code:
            return True
        from .online_payment_providers import provider_availability

        available, _ = provider_availability(channel_code)
        return available

    def get_provider_unavailable_reason(self, obj):
        if obj.code != "online":
            return None
        channel_code = self.context.get("channel_code", "")
        if not channel_code:
            return None
        from .online_payment_providers import provider_availability

        available, reason = provider_availability(channel_code)
        if not available:
            return reason
        return None


class BusinessPaymentMethodUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPaymentMethod
        fields = [
            "name",
            "fa_name",
            "icon_file",
            "point_to_channel_field",
            "requires_documents",
            "is_active",
        ]

    def validate(self, attrs):
        if "code" in self.initial_data:
            raise serializers.ValidationError(
                {"code": "Code is immutable."}
            )
        return attrs


class BusinessPaymentChannelWriteSerializer(serializers.ModelSerializer):
    payment_method_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=[],
        write_only=True,
    )

    class Meta:
        model = BusinessPaymentChannel
        fields = [
            "code",
            "name",
            "fa_name",
            "account_number",
            "card_number",
            "owner_name",
            "extra_data",
            "is_active",
            "logo_file",
            "payment_method_ids",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["code"].read_only = True

    def validate_payment_method_ids(self, value):
        if not value:
            return value
        methods = BusinessPaymentMethod.objects.filter(id__in=value)
        if methods.count() != len(value):
            raise serializers.ValidationError("Invalid payment method IDs.")
        return list(methods)

    def validate(self, attrs):
        if self.instance and self.instance.pk and "code" in self.initial_data:
            raise serializers.ValidationError(
                {"code": "Code is immutable."}
            )
        return attrs

    @property
    def supported_methods_value(self):
        return self.validated_data.get("payment_method_ids", [])


class ConfirmPaymentSerializer(serializers.Serializer):
    payment_method = serializers.CharField()
    payment_channel_id = serializers.IntegerField(min_value=1)
    ref_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    resource_account_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True,
        default=[],
    )

    def validate_payment_method(self, value):
        return value.strip().casefold()

    def validate_documents(self, documents):
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        errors = []
        for doc in documents:
            if doc.content_type not in allowed_types:
                errors.append(
                    f"{doc.name}: only JPEG, PNG, and WebP are allowed."
                )
            elif doc.size > 10 * 1024 * 1024:
                errors.append(
                    f"{doc.name}: file size must not exceed 10MB."
                )
        if errors:
            raise serializers.ValidationError(errors)
        return documents
