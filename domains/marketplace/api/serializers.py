from rest_framework import serializers

from ..models import BusinessOffer
from ..services import MarketplacePricingService


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
        cost_strategy = attrs.get(
            "cost_strategy", getattr(self.instance, "cost_strategy", None)
        )
        expected_profit = attrs.get(
            "expected_profit_percentage", getattr(self.instance, "expected_profit_percentage", None)
        )
        try:
            MarketplacePricingService.validate_offer_values(
                price=price,
                discount_type=discount_type,
                discount_value=discount_value,
                expected_profit_percentage=expected_profit,
                cost_strategy=cost_strategy,
            )
        except MarketplacePricingService.ValidationError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        return attrs
