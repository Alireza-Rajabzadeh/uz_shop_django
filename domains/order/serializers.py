from django.utils.translation import gettext as _
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
        fields = ["id", "name", "fa_name"]


class ConfirmPaymentSerializer(serializers.Serializer):
    payment_method = serializers.CharField()
    payment_channel_id = serializers.IntegerField()
    ref_number = serializers.CharField(
        required=False, allow_blank=True, max_length=128, default=""
    )
    resource_account_number = serializers.CharField(
        required=False, allow_blank=True, max_length=64, default=""
    )

    def validate_payment_method(self, value):
        normalized = value.strip().casefold()
        if normalized not in {"card_to_card", "deposit_to_account"}:
            raise serializers.ValidationError(
                _("This payment method is not available for manual payment.")
            )
        return normalized