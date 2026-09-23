import re

from rest_framework import serializers

from core.utils import CardNumberValidationError, normalize_card_number
from core.utils.transliteration import to_english_letters

from .models import (
    BusinessPayment,
    BusinessPaymentChannel,
    BusinessPaymentMethod,
    BusinessPaymentStatus,
)


class BaseListQuerySerializer(serializers.Serializer):
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


class ListQuerySerializer(BaseListQuerySerializer):
    has_point_to_channel = serializers.ChoiceField(
        choices=["true", "false"], required=False, allow_blank=True, default=""
    )

    def to_internal_value(self, data):
        result = super().to_internal_value(data)
        if result["has_point_to_channel"] == "true":
            result["has_point_to_channel"] = True
        elif result["has_point_to_channel"] == "false":
            result["has_point_to_channel"] = False
        else:
            result["has_point_to_channel"] = None
        return result


class ChannelListQuerySerializer(BaseListQuerySerializer):
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
            "description",
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


class BusinessPaymentChannelWriteSerializer(serializers.ModelSerializer):
    code = serializers.CharField(required=False, allow_blank=True, max_length=100)
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
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

    def validate_code(self, value):
        value = to_english_letters(value)
        if not value:
            return ""
        if not value.isascii():
            raise serializers.ValidationError(
                "Code must contain English letters only."
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]*", value):
            raise serializers.ValidationError(
                "Code must use English letters, digits, '_' or '-'."
            )
        existing = BusinessPaymentChannel.objects.filter(code=value)
        business = self.context.get("business")
        if business is not None:
            existing = existing.filter(business=business)
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "A channel with this code already exists."
            )
        return value

    def validate_name(self, value):
        value = to_english_letters(value)
        if value and not value.isascii():
            raise serializers.ValidationError(
                "Name must contain English letters only."
            )
        return value

    def validate_card_number(self, value):
        if value in (None, ""):
            return value
        try:
            return normalize_card_number(value)
        except CardNumberValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

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
        if self.instance and self.instance.pk and not attrs.get("name"):
            attrs.pop("name", None)
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
