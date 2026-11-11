from django.utils.translation import gettext as _
from rest_framework import serializers

from .services.address_info_service import AddressInfoService


class CartAddressWriteSerializer(serializers.Serializer):
    saved_address_id = serializers.IntegerField(required=False)
    receiver_name = serializers.CharField(required=False, max_length=100)
    receiver_phone = serializers.CharField(required=False, max_length=20)
    country_id = serializers.IntegerField(required=False)
    state_id = serializers.IntegerField(required=False)
    city_id = serializers.IntegerField(required=False)
    postal_code = serializers.CharField(required=False, max_length=20)
    address_line1 = serializers.CharField(required=False, max_length=255)
    address_line2 = serializers.CharField(required=False, max_length=255, allow_blank=True, default="")
    house_number = serializers.CharField(required=False, max_length=20, allow_blank=True, default="")

    MANUAL_REQUIRED = (
        "country_id",
        "state_id",
        "city_id",
        "postal_code",
        "address_line1",
        "receiver_name",
        "receiver_phone",
    )

    def validate(self, attrs):
        if attrs.get("saved_address_id") is not None:
            receiver_name = attrs.get("receiver_name")
            receiver_phone = attrs.get("receiver_phone")
            if (receiver_name is None) != (receiver_phone is None):
                raise serializers.ValidationError({
                    "receiver_name": _(
                        "Provide both receiver name and receiver phone, or neither."
                    )
                })
            attrs["mode"] = "saved"
            return attrs
        missing = [field for field in self.MANUAL_REQUIRED if attrs.get(field) is None]
        if missing:
            raise serializers.ValidationError({
                "address": _("Provide a saved address or fill the full address "
                             "(missing: %s).") % ", ".join(missing)
            })
        attrs["mode"] = "manual"
        return attrs


__all__ = [
    "CartAddressWriteSerializer",
    "AddressInfoService",
]
