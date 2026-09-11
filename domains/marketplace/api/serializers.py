from decimal import Decimal

from rest_framework import serializers

from core.constants import DISCOUNT_TYPES
from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
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
            "expected_profit_percentage",
            "cost_strategy",
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
        cost_strategy = attrs.get(
            "cost_strategy", getattr(self.instance, "cost_strategy", None)
        )
        if cost_strategy is not None and cost_strategy not in {m.value for m in VariantCostStrategyEnum}:
            raise serializers.ValidationError({
                "cost_strategy": "Unsupported pricing cost strategy."
            })
        expected_profit = attrs.get(
            "expected_profit_percentage", getattr(self.instance, "expected_profit_percentage", None)
        )
        if expected_profit is not None and expected_profit < 0:
            raise serializers.ValidationError({
                "expected_profit_percentage": "Expected profit percentage must be greater than or equal to zero."
            })
        return attrs
