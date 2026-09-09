from decimal import Decimal

from rest_framework import serializers

from core.constants import DISCOUNT_TYPES
from ..models import BusinessOffer


class BusinessOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessOffer
        fields = [
            "id",
            "business",
            "variant",
            "price",
            "discount_type",
            "discount_value",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        discount_type = attrs.get(
            "discount_type", getattr(self.instance, "discount_type", None)
        )
        discount_value = attrs.get(
            "discount_value", getattr(self.instance, "discount_value", None)
        )
        price = attrs.get("price", getattr(self.instance, "price", None))
        if bool(discount_type) != (discount_value is not None):
            raise serializers.ValidationError({
                "discount_value": "Discount type and value must be provided together."
            })
        if discount_type == "percentage" and discount_value is not None and discount_value > 100:
            raise serializers.ValidationError({
                "discount_value": "Percentage discount cannot exceed 100."
            })
        if discount_type == "fixed" and price is not None and discount_value is not None and discount_value > price:
            raise serializers.ValidationError({
                "discount_value": "Fixed discount cannot exceed the price."
            })
        return attrs
