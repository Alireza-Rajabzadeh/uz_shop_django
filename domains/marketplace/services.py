from decimal import Decimal

from django.db import transaction

from .models import BusinessOffer


class MarketplacePricingService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def get_active_offer(variant, business):
        return (
            BusinessOffer.objects.filter(
                variant=variant,
                business=business,
                is_active=True,
            )
            .select_related("business", "variant")
            .first()
        )

    @staticmethod
    def calculate_discounted_price(offer):
        if offer is None:
            return Decimal("0")
        if offer.discount_type == "percentage" and offer.discount_value:
            return offer.price - offer.price * offer.discount_value / Decimal("100")
        if offer.discount_type == "fixed" and offer.discount_value:
            return offer.price - offer.discount_value
        return offer.price

    @staticmethod
    def validate_offer_values(*, price, discount_type, discount_value, expected_profit_percentage, cost_strategy):
        cost_strategy = cost_strategy or "latest"
        if bool(discount_type) != (discount_value is not None):
            raise MarketplacePricingService.ValidationError({
                "discount_value": "Discount type and value must be provided together."
            })
        if discount_type == "percentage" and discount_value is not None and discount_value > 100:
            raise MarketplacePricingService.ValidationError({
                "discount_value": "Percentage discount cannot exceed 100."
            })
        if discount_type == "fixed" and price is not None and discount_value is not None and discount_value > price:
            raise MarketplacePricingService.ValidationError({
                "discount_value": "Fixed discount cannot exceed the price."
            })
        if expected_profit_percentage is not None and expected_profit_percentage < 0:
            raise MarketplacePricingService.ValidationError({
                "expected_profit_percentage": "Expected profit percentage must be greater than or equal to zero."
            })
        if cost_strategy not in {"latest", "weighted_average", "fifo_next"}:
            raise MarketplacePricingService.ValidationError({
                "cost_strategy": "Unsupported pricing cost strategy."
            })

    @classmethod
    @transaction.atomic
    def create_offer(cls, **values):
        cls.validate_offer_values(
            price=values.get("price"),
            discount_type=values.get("discount_type"),
            discount_value=values.get("discount_value"),
            expected_profit_percentage=values.get("expected_profit_percentage"),
            cost_strategy=values.get("cost_strategy"),
        )
        return BusinessOffer.objects.create(**values)

    @classmethod
    @transaction.atomic
    def update_offer(cls, offer, **values):
        merged = {
            "price": values.get("price", offer.price),
            "discount_type": values.get("discount_type", offer.discount_type),
            "discount_value": values.get("discount_value", offer.discount_value),
            "expected_profit_percentage": values.get(
                "expected_profit_percentage", offer.expected_profit_percentage
            ),
            "cost_strategy": values.get("cost_strategy", offer.cost_strategy),
        }
        cls.validate_offer_values(**merged)
        for field, value in values.items():
            setattr(offer, field, value)
        offer.save()
        return offer
