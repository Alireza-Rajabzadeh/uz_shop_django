from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, IntegerField, Q, Sum
from django.db.models.functions import Coalesce
from domains.catalog.models import ProductVariants
from django.utils.translation import gettext as _

from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
from domains.inventory.enums.VariantPriceHistorySourceEnum import (
    VariantPriceHistorySourceEnum,
)
from domains.inventory.models import (
    InventorySupply,
    VariantPriceHistory,
    VariantPricing,
)


class InventoryPricingService:
    # Per-variant pricing configuration plus read-only cost-basis and
    # suggested-price calculations. Nothing here writes to catalog prices;
    # results are computed on demand from received supply layers and never
    # persisted.

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def get_strategies(self):
        return [
            {"code": code, "name": name}
            for code, name in VariantCostStrategyEnum.choices()
        ]

    def get_variant_pricing(self, variant):
        return VariantPricing.objects.filter(variant=variant).first()

    @transaction.atomic
    def update_variant_pricing(self, variant, *, expected_profit_percentage=None, cost_strategy=None):
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

        pricing = VariantPricing.objects.select_for_update().filter(variant=variant).first()
        if pricing is None:
            pricing = VariantPricing(variant=variant)
        if expected_profit_percentage is not None:
            pricing.expected_profit_percentage = Decimal(str(expected_profit_percentage))
        if cost_strategy is not None:
            pricing.cost_strategy = cost_strategy
        pricing.save()
        return pricing

    @transaction.atomic
    def apply_price(self, variant, *, price=None):
        variant = (
            ProductVariants.objects.select_for_update()
            .select_related("product")
            .get(pk=variant.pk)
        )
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

        old_price = Decimal(variant.price)
        variant.price = new_price
        variant.save(update_fields=["price"])
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

    def _pricing_context(self, variant):
        config = self.get_variant_pricing(variant)
        rows = list(self._received_supplies_with_remaining(variant)) if config is not None else []
        return config, rows

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
        return self._calculate_basis(config.cost_strategy, rows)

    def get_suggested_price(self, variant):
        config, rows = self._pricing_context(variant)
        if config is None or not rows:
            return None
        basis = self._calculate_basis(config.cost_strategy, rows)
        profit = Decimal(config.expected_profit_percentage)
        return basis * (Decimal("1") + profit / Decimal("100"))

    def get_pricing_summary(self, variant):
        config, rows = self._pricing_context(variant)
        if config is None:
            return None
        basis = self._calculate_basis(config.cost_strategy, rows) if rows else None
        suggested_price = (
            basis * (Decimal("1") + Decimal(config.expected_profit_percentage) / Decimal("100"))
            if basis is not None
            else None
        )
        money = Decimal("0.01")
        return {
            "strategy": config.cost_strategy,
            "expected_profit_percentage": config.expected_profit_percentage,
            "cost_basis": basis.quantize(money) if basis is not None else None,
            "suggested_price": suggested_price.quantize(money) if suggested_price is not None else None,
            "available_supply_quantity": sum(row.remaining_quantity for row in rows),
            "catalog_price": getattr(variant, "price", None),
        }

    # ─────────────────── admin pricing overview / list ───────────────────

    @staticmethod
    def _quantized(value):
        return value.quantize(Decimal("0.01")) if value is not None else None

    def _overview_for_rows(self, variant, config, rows):
        """Shared overview builder; rows must be newest-first and annotated."""
        latest_cost = self._landed_unit_cost(rows[0]) if rows else None
        fifo_next_cost = self._landed_unit_cost(rows[-1]) if rows else None
        weighted_average_cost = (
            self._calculate_basis(VariantCostStrategyEnum.WEIGHTED_AVERAGE.value, rows)
            if rows
            else None
        )
        selected_basis = (
            self._calculate_basis(config.cost_strategy, rows)
            if config is not None and rows
            else None
        )
        suggested_price = (
            selected_basis * (Decimal("1") + Decimal(config.expected_profit_percentage) / Decimal("100"))
            if selected_basis is not None
            else None
        )
        return {
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_name": variant.product.name,
            "current_price": getattr(variant, "price", None),
            "latest_cost": self._quantized(latest_cost),
            "weighted_average_cost": self._quantized(weighted_average_cost),
            "fifo_next_cost": self._quantized(fifo_next_cost),
            "cost_strategy": config.cost_strategy if config is not None else None,
            "expected_profit_percentage": (
                config.expected_profit_percentage if config is not None else None
            ),
            "cost_basis": self._quantized(selected_basis),
            "suggested_price": self._quantized(suggested_price),
            "total_remaining_supply_quantity": sum(row.remaining_quantity for row in rows),
            "catalog_price": getattr(variant, "price", None),
            "created_at": config.created_at if config is not None else None,
            "updated_at": config.updated_at if config is not None else None,
        }

    def get_variant_pricing_overview(self, variant):
        config, rows = self._pricing_context(variant)
        return self._overview_for_rows(variant, config, rows)

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
            queryset = queryset.filter(pk__in=VariantPricing.objects.filter(
                cost_strategy=strategy
            ).values_list("variant_id", flat=True))
        if has_pricing is not None:
            configured_ids = VariantPricing.objects.values_list("variant_id", flat=True)
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
            )
        )
        ordering_map = {
            "sku": "sku",
            "product_name": "product__name",
            "current_price": "price",
            "remaining_quantity": "remaining_quantity_total",
        }
        requested = (ordering or "sku").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"), "sku")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def get_pricing_overview_map(self, variants):
        """Batch overview for one page of variants (constant query count)."""
        variant_ids = [variant.id for variant in variants]
        configs = {
            pricing.variant_id: pricing
            for pricing in VariantPricing.objects.filter(variant_id__in=variant_ids)
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
                variant, configs.get(variant.id), rows_by_variant.get(variant.id, [])
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
