from django.utils.translation import gettext as _
from rest_framework import serializers


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