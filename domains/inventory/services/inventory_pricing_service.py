from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from domains.business.models import BusinessProfile
from domains.catalog.models import ProductVariants
from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
from domains.inventory.enums.VariantPriceHistorySourceEnum import (
    VariantPriceHistorySourceEnum,
)
from domains.inventory.models import (
    InventorySupply,
    VariantPriceHistory,
)
from domains.inventory.services.price_history_mongo import log_price_change
from domains.marketplace.models import BusinessOffer, PricingStrategy
from domains.marketplace.models.offer_price_history import SOURCE_ADMIN
from domains.marketplace.services import MarketplacePricingService

# BusinessOffer.is_active is the marketplace *listing* flag only. Pricing
# configuration (expected_profit_percentage, cost_strategy) and the offer price
# live on the same row, so every read/write below uses any offer for the
# variant — active or draft. Only customer-facing readers (storefront, cart,
# order, catalog search) and financial reporting keep the is_active=True filter.


class InventoryPricingService:
    # Per-business-variant pricing configuration plus read-only cost-basis
    # and suggested-price calculations. Pricing config (expected_profit_percentage,
    # cost_strategy) lives on BusinessOffer, not on a shared VariantPricing model.

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def get_strategies(self):
        # Display data comes from the PricingStrategy reference table, not the
        # enum: the rows carry the Persian labels and the user-guide document
        # the panels render. Codes themselves stay validated against
        # strategy_codes() so the table and enum cannot drift apart unnoticed.
        return [
            {"code": item.code, "name": item.name, "fa_name": item.fa_name, "description": item.description}
            for item in PricingStrategy.objects.all()
        ]

    def get_variant_pricing(self, variant, business=None):
        """Return the BusinessOffer holding this variant's pricing config.

        Any offer qualifies: a draft (inactive) offer stores the same
        strategy/profit configuration as a listed one, and the marketplace
        listing flag must not decide whether the vendor can read their config.
        Callers that know their business scope the lookup to it, because the
        unique constraint is (business, variant) rather than variant alone.
        """
        offers = BusinessOffer.objects.filter(variant=variant)
        if business is not None:
            offers = offers.filter(business=business)
        return offers.first()

    def _resolve_config_business(self, business):
        """Business that owns a newly created configuration offer.

        The vendor view passes its own business. The admin pricing endpoint has
        no business context, so it falls back to the singleton profile and
        refuses to guess when the database holds more than one.
        """
        if business is not None:
            return business
        businesses = BusinessProfile.objects.order_by("id")
        count = businesses.count()
        if count == 1:
            return businesses.first()
        if count > 1:
            raise self.ValidationError({
                "pricing": [
                    _(
                        "Multiple business profiles exist, so the business "
                        "that owns this pricing configuration must be identified."
                    )
                ]
            })
        return None

    def _strategy_row(self, code):
        """Resolve a validated strategy code to its PricingStrategy row.

        The code was already checked against strategy_codes(); this only maps
        it onto the FK and turns table drift into a 400 instead of a 500.
        """
        try:
            return MarketplacePricingService.resolve_strategies({"cost_strategy": code})["cost_strategy"]
        except MarketplacePricingService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc

    @transaction.atomic
    def update_variant_pricing(
        self,
        variant,
        *,
        expected_profit_percentage=None,
        cost_strategy=None,
        business=None,
        source=SOURCE_ADMIN,
    ):
        if cost_strategy is not None and cost_strategy not in self.strategy_codes():
            raise self.ValidationError({
                "cost_strategy": [_('Unsupported pricing cost strategy.')]
            })
        if expected_profit_percentage is not None:
            profit = Decimal(str(expected_profit_percentage))
            if profit < 0:
                raise self.ValidationError({
                    "expected_profit_percentage": [
                        _('Expected profit percentage must be greater than or equal to zero.')
                    ]
                })

        offers = BusinessOffer.objects.select_for_update().filter(variant=variant)
        if business is not None:
            offers = offers.filter(business=business)
        offer = offers.first()
        if offer is None:
            # Saving a strategy must not require a marketplace offer: the
            # config itself is the thing being created. The draft stays
            # inactive, so it is never visible to customers until the vendor
            # presses Active.
            business = self._resolve_config_business(business)
            if business is None:
                raise self.ValidationError({
                    "pricing": [
                        _(
                            "No business profile exists, so the pricing "
                            "configuration cannot be stored."
                        )
                    ]
                })
            values = {
                "business": business,
                "variant": variant,
                "is_active": False,
            }
            if expected_profit_percentage is not None:
                values["expected_profit_percentage"] = Decimal(str(expected_profit_percentage))
            if cost_strategy is not None:
                values["cost_strategy"] = cost_strategy
            try:
                return MarketplacePricingService.create_offer(_source=source, **values)
            except MarketplacePricingService.ValidationError as exc:
                raise self.ValidationError(exc.errors) from exc
        if expected_profit_percentage is not None:
            offer.expected_profit_percentage = Decimal(str(expected_profit_percentage))
        if cost_strategy is not None:
            offer.cost_strategy = self._strategy_row(cost_strategy)
        offer.save(update_fields=["expected_profit_percentage", "cost_strategy", "updated_at"])
        return offer

    @transaction.atomic
    def apply_price(self, variant, *, price=None):
        variant = (
            ProductVariants.objects.select_for_update()
            .select_related("product")
            .get(pk=variant.pk)
        )
        offer = BusinessOffer.objects.filter(
            variant=variant
        ).select_for_update().first()
        if offer is None:
            raise self.ValidationError({
                "pricing": [
                    _(
                        "No business offer exists for this variant. "
                        "Save a price or a pricing strategy first."
                    )
                ]
            })

        overview = self.get_variant_pricing_overview(variant)
        cost_basis = overview["cost_basis"]
        suggested_price = overview["suggested_price"]
        if cost_basis is None or suggested_price is None:
            raise self.ValidationError({
                "pricing": [
                    _(
                        "A configured pricing strategy and available received supply "
                        "are required before applying a price."
                    )
                ]
            })

        custom_price = price is not None
        new_price = Decimal(str(price if custom_price else suggested_price)).quantize(
            Decimal("0.01")
        )
        if new_price < 0:
            raise self.ValidationError({
                "price": [_('Price must be greater than or equal to zero.')]
            })

        old_price = Decimal(offer.price)
        offer.price = new_price
        offer.save(update_fields=["price"])
        history = VariantPriceHistory.objects.create(
            variant=variant,
            old_price=old_price,
            new_price=new_price,
            cost_basis=cost_basis,
            cost_strategy=overview["cost_strategy"],
            expected_profit_percentage=overview["expected_profit_percentage"],
            source=(
                VariantPriceHistorySourceEnum.MANUAL.value
                if custom_price
                else VariantPriceHistorySourceEnum.INVENTORY_PRICING.value
            ),
        )
        log_price_change(
            variant_id=variant.id,
            sku=variant.sku,
            product_name=variant.product.name,
            old_price=old_price,
            new_price=new_price,
            cost_basis=cost_basis,
            cost_strategy=overview["cost_strategy"],
            expected_profit_percentage=overview["expected_profit_percentage"],
            source=history.source,
        )
        return variant, history

    def get_price_history(self, variant):
        return VariantPriceHistory.objects.filter(variant=variant).order_by(
            "-created_at", "-id"
        )

    @staticmethod
    def strategy_codes():
        return {member.value for member in VariantCostStrategyEnum}

    # ───────────────────── cost basis calculation ─────────────────────

    def _received_supplies_with_remaining(self, variant):
        # Newest first; a single JOIN aggregate avoids per-supply cost queries.
        # Landed-unit math mirrors InventoryCostService formulas.
        return InventorySupply.objects.filter(
            variant=variant,
            received_at__isnull=False,
            remaining_quantity__gt=0,
        ).annotate(
            extra_cost_total=Coalesce(
                Sum("costs__amount"),
                Decimal("0"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        ).order_by("-supplied_at", "-id")

    @staticmethod
    def _landed_unit_cost(row):
        base_cost_total = Decimal(row.unit_buy_price) * Decimal(row.quantity)
        return (base_cost_total + Decimal(row.extra_cost_total)) / Decimal(row.quantity)

    def calculate_landed_unit_cost(self, row):
        """Public landed-unit-cost hook for sibling services (reports, etc.)."""
        return self._landed_unit_cost(row)

    def calculate_basis(self, strategy, rows):
        """Public cost-basis hook for sibling services (reports, etc.)."""
        return self._calculate_basis(strategy, rows)

    def _pricing_context(self, variant, business=None):
        # Supply rows are always loaded: costs are derived from received
        # supplies, so they must render even before any pricing config exists.
        return self.get_variant_pricing(variant, business=business), list(
            self._received_supplies_with_remaining(variant)
        )

    def _calculate_basis(self, strategy, rows):
        if strategy == VariantCostStrategyEnum.WEIGHTED_AVERAGE.value:
            total_value = Decimal("0")
            total_quantity = 0
            for row in rows:
                total_value += Decimal(row.remaining_quantity) * self._landed_unit_cost(row)
                total_quantity += row.remaining_quantity
            return total_value / Decimal(total_quantity)
        if strategy == VariantCostStrategyEnum.FIFO_NEXT.value:
            return self._landed_unit_cost(rows[-1])
        return self._landed_unit_cost(rows[0])

    def get_cost_basis(self, variant):
        config, rows = self._pricing_context(variant)
        if config is None or not rows:
            return None
        return self._calculate_basis(config.cost_strategy.code, rows)

    def get_suggested_price(self, variant):
        config, rows = self._pricing_context(variant)
        if config is None or not rows:
            return None
        basis = self._calculate_basis(config.cost_strategy.code, rows)
        profit = Decimal(config.expected_profit_percentage)
        return basis * (Decimal("1") + profit / Decimal("100"))

    def get_pricing_summary(self, variant):
        config, rows = self._pricing_context(variant)
        if config is None:
            return None
        basis = self._calculate_basis(config.cost_strategy.code, rows) if rows else None
        suggested_price = (
            basis * (Decimal("1") + Decimal(config.expected_profit_percentage) / Decimal("100"))
            if basis is not None
            else None
        )
        money = Decimal("0.01")
        return {
            "strategy": config.cost_strategy.code,
            "expected_profit_percentage": config.expected_profit_percentage,
            "cost_basis": basis.quantize(money) if basis is not None else None,
            "suggested_price": suggested_price.quantize(money) if suggested_price is not None else None,
            "available_supply_quantity": sum(row.remaining_quantity for row in rows),
            "catalog_price": config.price,
        }

    # ─────────────────── admin pricing overview / list ───────────────────

    @staticmethod
    def _quantized(value):
        return value.quantize(Decimal("0.01")) if value is not None else None

    def _overview_for_rows(
        self,
        variant,
        config,
        rows,
        offer_price=None,
        *,
        cost_strategy=None,
        expected_profit_percentage=None,
    ):
        """Shared overview builder; rows must be newest-first and annotated.

        `cost_strategy` / `expected_profit_percentage` are unsaved overrides for
        the calculate/preview flow: when present they win over the stored
        config, and the response echoes the effective values so the caller can
        label the numbers as a preview instead of saved state.
        """
        if offer_price is None:
            offer_price = config.price if config is not None else None
        effective_strategy = (
            cost_strategy
            if cost_strategy is not None
            else (config.cost_strategy.code if config is not None else None)
        )
        effective_profit = (
            expected_profit_percentage
            if expected_profit_percentage is not None
            else (config.expected_profit_percentage if config is not None else None)
        )
        latest_cost = self._landed_unit_cost(rows[0]) if rows else None
        fifo_next_cost = self._landed_unit_cost(rows[-1]) if rows else None
        weighted_average_cost = (
            self._calculate_basis(VariantCostStrategyEnum.WEIGHTED_AVERAGE.value, rows)
            if rows
            else None
        )
        selected_basis = (
            self._calculate_basis(effective_strategy, rows)
            if effective_strategy is not None and rows
            else None
        )
        suggested_price = (
            selected_basis
            * (Decimal("1") + Decimal(effective_profit) / Decimal("100"))
            if selected_basis is not None and effective_profit is not None
            else None
        )
        return {
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_name": variant.product.name,
            "current_price": offer_price,
            "latest_cost": self._quantized(latest_cost),
            "weighted_average_cost": self._quantized(weighted_average_cost),
            "fifo_next_cost": self._quantized(fifo_next_cost),
            "cost_strategy": effective_strategy,
            "expected_profit_percentage": effective_profit,
            "cost_basis": self._quantized(selected_basis),
            "suggested_price": self._quantized(suggested_price),
            "total_remaining_supply_quantity": sum(row.remaining_quantity for row in rows),
            "catalog_price": offer_price,
            "created_at": config.created_at if config is not None else None,
            "updated_at": config.updated_at if config is not None else None,
        }

    def get_variant_pricing_overview(
        self,
        variant,
        *,
        business=None,
        cost_strategy=None,
        expected_profit_percentage=None,
    ):
        config, rows = self._pricing_context(variant, business=business)
        return self._overview_for_rows(
            variant,
            config,
            rows,
            cost_strategy=cost_strategy,
            expected_profit_percentage=expected_profit_percentage,
        )

    def search_pricing(
        self,
        *,
        search=None,
        category_id=None,
        strategy=None,
        has_pricing=None,
        ordering=None,
    ):
        queryset = ProductVariants.objects.select_related("product")
        if search:
            queryset = queryset.filter(
                Q(sku__icontains=search) | Q(product__name__icontains=search)
            )
        if category_id is not None:
            # Subquery keeps the supplies aggregate free of M2M row duplication.
            queryset = queryset.filter(pk__in=ProductVariants.objects.filter(
                product__categories__id=category_id
            ).values_list("pk", flat=True))
        if strategy is not None:
            if strategy not in self.strategy_codes():
                raise self.ValidationError({
                    "strategy": [_('Unsupported pricing cost strategy.')]
                })
            queryset = queryset.filter(pk__in=BusinessOffer.objects.filter(
                cost_strategy__code=strategy
            ).values_list("variant_id", flat=True))
        if has_pricing is not None:
            # Pricing config lives on any offer, active or draft, so "has
            # pricing" must not silently drop variants that are not listed yet.
            configured_ids = BusinessOffer.objects.all().values_list(
                "variant_id", flat=True
            )
            queryset = (
                queryset.filter(pk__in=configured_ids)
                if has_pricing
                else queryset.exclude(pk__in=configured_ids)
            )

        remaining_filter = Q(
            inventory_supplies__received_at__isnull=False,
            inventory_supplies__remaining_quantity__gt=0,
        )
        queryset = queryset.annotate(
            remaining_quantity_total=Coalesce(
                Sum(
                    "inventory_supplies__remaining_quantity",
                    filter=remaining_filter,
                ),
                0,
                output_field=IntegerField(),
            ),
            current_price_annotation=Coalesce(
                Subquery(
                    BusinessOffer.objects.filter(
                        variant=OuterRef("pk"),
                    ).values("price")[:1],
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                ),
                Decimal("0"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        )
        ordering_map = {
            "sku": "sku",
            "product_name": "product__name",
            "remaining_quantity": "remaining_quantity_total",
            "current_price": "current_price_annotation",
        }
        requested = (ordering or "sku").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"), "sku")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def get_pricing_overview_map(self, variants):
        """Batch overview for one page of variants (constant query count)."""
        variant_ids = [variant.id for variant in variants]
        offers = {
            offer.variant_id: offer
            for offer in BusinessOffer.objects.filter(
                variant_id__in=variant_ids,
            )
        }
        rows_by_variant = defaultdict(list)
        supplies = InventorySupply.objects.filter(
            variant_id__in=variant_ids,
            received_at__isnull=False,
            remaining_quantity__gt=0,
        ).annotate(
            extra_cost_total=Coalesce(
                Sum("costs__amount"),
                Decimal("0"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        ).order_by("variant_id", "-supplied_at", "-id")
        for supply in supplies:
            rows_by_variant[supply.variant_id].append(supply)
        return {
            variant.id: self._overview_for_rows(
                variant, offers.get(variant.id), rows_by_variant.get(variant.id, []),
            )
            for variant in variants
        }

    def serialize_pricing_row(self, variant, overview):
        return {
            "variant_id": overview["variant_id"],
            "sku": overview["sku"],
            "product_name": overview["product_name"],
            "current_price": overview["current_price"],
            "cost_strategy": overview["cost_strategy"],
            "expected_profit_percentage": overview["expected_profit_percentage"],
            "cost_basis": overview["cost_basis"],
            "suggested_price": overview["suggested_price"],
            "remaining_quantity": overview["total_remaining_supply_quantity"],
        }
