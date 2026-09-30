from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _

from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum

from .models import BusinessOffer, OfferPriceHistory, PricingStrategy
from .models.offer_price_history import SOURCE_ADMIN

# The enum is the vocabulary: it validates incoming codes, seeds the
# PricingStrategy table, and drives the cost-basis formulas. The table only
# carries display data (labels and the user guide), so a code must exist in
# both places — domains.marketplace.tests_pricing_strategy asserts that.
COST_STRATEGY_CODES = {member.value for member in VariantCostStrategyEnum}


class MarketplacePricingService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    # Fields whose explicit None means "clear this value". Any field omitted
    # from the values mapping keeps whatever the offer already holds.
    WRITABLE_FIELDS = (
        "price",
        "discount_type",
        "discount_value",
        "expected_profit_percentage",
        "cost_strategy",
    )

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
    def strategy_code(value):
        # BusinessOffer.cost_strategy is a PricingStrategy FK, but everything
        # above the persistence layer (serializers, validation, audit rows)
        # speaks the plain code string. Accept either form.
        return getattr(value, "code", value)

    @staticmethod
    def resolve_strategies(values):
        """Turn `cost_strategy` code strings into PricingStrategy rows.

        The two write funnels — admin offers and the vendor variant API — both
        arrive here with a code, while the model needs a row. Raises the same
        ValidationError validate_offer_values() raises so callers keep mapping
        it to a 400.
        """
        strategy = values.get("cost_strategy")
        if strategy is None or isinstance(strategy, PricingStrategy):
            return values
        try:
            values["cost_strategy"] = PricingStrategy.objects.get(code=strategy)
        except PricingStrategy.DoesNotExist as exc:
            raise MarketplacePricingService.ValidationError({
                "cost_strategy": _("Unsupported pricing cost strategy.")
            }) from exc
        return values

    @classmethod
    def validate_offer_values(cls, *, price, discount_type, discount_value, expected_profit_percentage, cost_strategy):
        cost_strategy = cls.strategy_code(cost_strategy) or "latest"
        if bool(discount_type) != (discount_value is not None):
            raise MarketplacePricingService.ValidationError({
                "discount_value": _("Discount type and value must be provided together.")
            })
        if discount_type == "percentage" and discount_value is not None and discount_value > 100:
            raise MarketplacePricingService.ValidationError({
                "discount_value": _("Percentage discount cannot exceed 100.")
            })
        if discount_type == "fixed" and price is not None and discount_value is not None and discount_value > price:
            raise MarketplacePricingService.ValidationError({
                "discount_value": _("Fixed discount cannot exceed the price.")
            })
        if expected_profit_percentage is not None and expected_profit_percentage < 0:
            raise MarketplacePricingService.ValidationError({
                "expected_profit_percentage": _(
                    "Expected profit percentage must be greater than or equal to zero."
                )
            })
        if cost_strategy not in COST_STRATEGY_CODES:
            raise MarketplacePricingService.ValidationError({
                "cost_strategy": _("Unsupported pricing cost strategy.")
            })

    @classmethod
    def _merge_values(cls, offer, values):
        # An explicit None clears the field; an omitted key keeps the stored value.
        merged = {}
        for field in cls.WRITABLE_FIELDS:
            if field in values:
                merged[field] = values[field]
            elif offer is not None:
                merged[field] = getattr(offer, field)
            else:
                merged[field] = None
        return merged

    @classmethod
    def _record_history(
        cls,
        offer,
        *,
        old_price,
        old_discount_type,
        old_discount_value,
        source=SOURCE_ADMIN,
    ):
        if (
            old_price == offer.price
            and old_discount_type == offer.discount_type
            and old_discount_value == offer.discount_value
        ):
            return None
        return OfferPriceHistory.objects.create(
            offer=offer,
            business=offer.business,
            variant=offer.variant,
            old_price=old_price,
            new_price=offer.price,
            old_discount_type=old_discount_type,
            new_discount_type=offer.discount_type,
            old_discount_value=old_discount_value,
            new_discount_value=offer.discount_value,
            cost_strategy=cls.strategy_code(offer.cost_strategy),
            expected_profit_percentage=offer.expected_profit_percentage,
            source=source,
        )

    @classmethod
    @transaction.atomic
    def create_offer(cls, *, _source=SOURCE_ADMIN, **values):
        cls.validate_offer_values(**cls._merge_values(None, values))
        offer = BusinessOffer.objects.create(**cls.resolve_strategies(values))
        cls._record_history(
            offer,
            old_price=Decimal("0"),
            old_discount_type=None,
            old_discount_value=None,
            source=_source,
        )
        return offer

    @classmethod
    @transaction.atomic
    def update_offer(cls, offer, *, _source=SOURCE_ADMIN, **values):
        cls.validate_offer_values(**cls._merge_values(offer, values))
        previous = {
            "price": offer.price,
            "discount_type": offer.discount_type,
            "discount_value": offer.discount_value,
        }
        # Only keys present in `values` are written: an omitted field keeps its
        # stored value, an explicit None clears it. Pass-through fields such as
        # is_active, business and variant ride along untouched.
        for field, value in cls.resolve_strategies(values).items():
            setattr(offer, field, value)
        offer.save()
        cls._record_history(
            offer,
            old_price=previous["price"],
            old_discount_type=previous["discount_type"],
            old_discount_value=previous["discount_value"],
            source=_source,
        )
        return offer

    @classmethod
    def get_price_history(cls, variant, business=None, limit=50):
        history = OfferPriceHistory.objects.filter(variant=variant)
        if business is not None:
            history = history.filter(business=business)
        return list(history.select_related("offer")[:limit])
