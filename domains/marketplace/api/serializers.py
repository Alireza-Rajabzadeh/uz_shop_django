from rest_framework import serializers

from domains.order.serializers import (
    AdminOrderStatusSerializer,
    ReturnRequestCreateSerializer,
    ReturnRequestEvidenceSerializer,
    ReturnRequestItemSerializer,
    ReturnRequestSerializer,
)

from ..models import (
    BusinessOffer,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
    MarketplaceReturnRequestEvidence,
    MarketplaceReturnRequestItem,
    OfferPriceHistory,
    PricingStrategy,
)
from ..services import MarketplacePricingService


class BusinessOfferSerializer(serializers.ModelSerializer):
    # cost_strategy is a PricingStrategy FK, but the API contract is the code
    # string ("latest", ...). A plain ModelSerializer would leak the row id
    # here and start accepting ids, so both directions are pinned to `code`.
    # required=False mirrors the old CharField default: omitting the field on
    # create falls back to BusinessOffer's "latest" default.
    cost_strategy = serializers.SlugRelatedField(
        slug_field="code",
        queryset=PricingStrategy.objects.all(),
        required=False,
    )

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


class OfferPriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferPriceHistory
        fields = [
            "id",
            "offer",
            "variant",
            "old_price",
            "new_price",
            "old_discount_type",
            "new_discount_type",
            "old_discount_value",
            "new_discount_value",
            "cost_strategy",
            "expected_profit_percentage",
            "source",
            "created_at",
        ]
        read_only_fields = fields


# ───────────────────────── returns ─────────────────────────
# The shape of a return request is identical on either flow, so the shop's
# serializers are subclassed purely to name the marketplace tables rather
# than restated.


class MarketplaceReturnRequestItemSerializer(ReturnRequestItemSerializer):
    class Meta(ReturnRequestItemSerializer.Meta):
        model = MarketplaceReturnRequestItem


class MarketplaceReturnRequestEvidenceSerializer(ReturnRequestEvidenceSerializer):
    class Meta(ReturnRequestEvidenceSerializer.Meta):
        model = MarketplaceReturnRequestEvidence


class MarketplaceReturnRequestSerializer(ReturnRequestSerializer):
    items = MarketplaceReturnRequestItemSerializer(many=True, read_only=True)
    evidence = MarketplaceReturnRequestEvidenceSerializer(many=True, read_only=True)

    class Meta(ReturnRequestSerializer.Meta):
        model = MarketplaceReturnRequest


class MarketplaceReturnRequestCreateSerializer(ReturnRequestCreateSerializer):
    # Restated only so the choices come from this flow's model; the values
    # themselves are the same two refund destinations either way.
    refund_destination_type = serializers.ChoiceField(
        choices=MarketplaceReturnRequest.RefundDestinationType.choices
    )


# ───────────────────────── admin order filters ─────────────────────────


class AdminMarketplaceOrderStatusSerializer(AdminOrderStatusSerializer):
    class Meta(AdminOrderStatusSerializer.Meta):
        model = MarketplaceOrderStatus
