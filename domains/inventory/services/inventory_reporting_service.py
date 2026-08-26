from collections import defaultdict
from decimal import Decimal

from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Sum,
    Subquery,
)
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from domains.catalog.models import ProductVariants
from domains.inventory.models import (
    InventorySupply,
    InventorySupplyConsumption,
    VariantPricing,
)
from domains.inventory.services.inventory_pricing_service import InventoryPricingService


class InventoryReportingService:
    # Read-only financial reporting over received supply layers and active
    # consumption records. Reporting never mutates stock, supplies, prices,
    # or pricing configuration.

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def __init__(self):
        self.pricing_service = InventoryPricingService()

    # ───────────────────────── shared query builders ─────────────────────────

    @staticmethod
    def _received_supplies_queryset():
        return InventorySupply.objects.filter(received_at__isnull=False).annotate(
            extra_cost_total=Coalesce(
                Sum("costs__amount"),
                Decimal("0"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        )

    @staticmethod
    def _effective_quantity_expression():
        return ExpressionWrapper(
            F("quantity") - F("reversed_quantity"),
            output_field=IntegerField(),
        )

    def _consumption_stats_by_variant(self, variant_ids):
        return {
            row["order_item__variant_id"]: row
            for row in InventorySupplyConsumption.objects.filter(
                order_item__variant_id__in=variant_ids
            ).values("order_item__variant_id").annotate(
                consumed_quantity=Sum(self._effective_quantity_expression()),
                total_cogs=Sum(
                    ExpressionWrapper(
                        self._effective_quantity_expression() * F("unit_cost"),
                        output_field=DecimalField(max_digits=22, decimal_places=2),
                    )
                ),
            )
        }

    # ─────────────────────────── summary report ───────────────────────────

    def get_summary(self):
        money = Decimal("0.01")
        # Value decomposes linearly so the costs JOIN cannot double-count:
        #   SUM(remaining × unit_buy_price)
        # + SUM(remaining × extra_cost / quantity)   -- NULL rows are skipped by SUM
        received_supplies = InventorySupply.objects.filter(received_at__isnull=False)
        supply_totals = received_supplies.aggregate(
            remaining_quantity_total=Sum("remaining_quantity"),
            base_value=Sum(
                ExpressionWrapper(
                    F("remaining_quantity") * F("unit_buy_price"),
                    output_field=DecimalField(max_digits=28, decimal_places=2),
                )
            ),
            extra_value=Sum(
                ExpressionWrapper(
                    F("remaining_quantity") * F("costs__amount") / F("quantity"),
                    output_field=DecimalField(max_digits=28, decimal_places=8),
                )
            ),
        )
        base_value = supply_totals["base_value"] or Decimal("0")
        extra_value = supply_totals["extra_value"] or Decimal("0")
        inventory_cost_value = (base_value + extra_value).quantize(money)
        consumption_totals = InventorySupplyConsumption.objects.aggregate(
            total_cogs=Sum(
                ExpressionWrapper(
                    self._effective_quantity_expression() * F("unit_cost"),
                    output_field=DecimalField(max_digits=22, decimal_places=2),
                )
            ),
        )
        total_cogs = consumption_totals["total_cogs"] or Decimal("0")
        estimated_revenue = self._estimate_revenue().quantize(money)
        estimated_profit = estimated_revenue - total_cogs.quantize(money)
        return {
            "inventory_cost_value": inventory_cost_value,
            "remaining_supply_quantity": supply_totals["remaining_quantity_total"] or 0,
            "total_cogs": total_cogs.quantize(money),
            "estimated_revenue": estimated_revenue,
            "estimated_profit": estimated_profit.quantize(money),
        }

    def _estimate_revenue(self):
        # Sold units valued at the current suggested price of their variant
        # (catalog price as fallback); unpriced variants contribute nothing.
        per_variant = list(
            InventorySupplyConsumption.objects.values("order_item__variant_id")
            .annotate(effective_quantity=Sum(self._effective_quantity_expression()))
            .order_by()
        )
        variant_ids = [row["order_item__variant_id"] for row in per_variant]
        if not variant_ids:
            return Decimal("0")
        variants = ProductVariants.objects.in_bulk(variant_ids)
        revenue = Decimal("0")
        for row in per_variant:
            variant = variants.get(row["order_item__variant_id"])
            if variant is None:
                continue
            suggested_price = self.pricing_service.get_suggested_price(variant)
            unit_revenue = (
                suggested_price
                if suggested_price is not None
                else getattr(variant, "price", None)
            )
            if unit_revenue is None:
                continue
            revenue += Decimal(row["effective_quantity"]) * Decimal(unit_revenue)
        return revenue

    # ─────────────────────────── variant report ───────────────────────────

    def search_variants_for_report(
        self, *, search=None, category_id=None, strategy=None, ordering=None
    ):
        queryset = ProductVariants.objects.select_related("product")
        if search:
            queryset = queryset.filter(
                Q(sku__icontains=search) | Q(product__name__icontains=search)
            )
        if category_id is not None:
            # Subquery keeps the supplies aggregate free of M2M duplication.
            queryset = queryset.filter(pk__in=ProductVariants.objects.filter(
                product__categories__id=category_id
            ).values_list("pk", flat=True))
        if strategy is not None:
            if strategy not in InventoryPricingService.strategy_codes():
                raise self.ValidationError({
                    "strategy": [_('Unsupported pricing cost strategy.')]
                })
            queryset = queryset.filter(pk__in=VariantPricing.objects.filter(
                cost_strategy=strategy
            ).values_list("variant_id", flat=True))

        scoped_consumptions = InventorySupplyConsumption.objects.filter(
            order_item__variant=OuterRef("pk")
        )
        effective = self._effective_quantity_expression()
        queryset = queryset.annotate(
            remaining_quantity_total=Coalesce(
                Sum(
                    "inventory_supplies__remaining_quantity",
                    filter=Q(
                        inventory_supplies__received_at__isnull=False,
                        inventory_supplies__remaining_quantity__gt=0,
                    ),
                ),
                0,
                output_field=IntegerField(),
            ),
            total_consumed_quantity=Coalesce(
                Subquery(
                    scoped_consumptions.annotate(
                        value=Sum(effective)
                    ).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
            total_cogs=Coalesce(
                Subquery(
                    scoped_consumptions.annotate(
                        value=Sum(
                            ExpressionWrapper(
                                effective * F("unit_cost"),
                                output_field=DecimalField(
                                    max_digits=22, decimal_places=2
                                ),
                            )
                        )
                    ).values("value")[:1],
                    output_field=DecimalField(max_digits=22, decimal_places=2),
                ),
                Decimal("0"),
                output_field=DecimalField(max_digits=22, decimal_places=2),
            ),
        )

        ordering_map = {
            "sku": "sku",
            "product_name": "product__name",
            "current_price": "price",
            "remaining_quantity": "remaining_quantity_total",
            "total_consumed_quantity": "total_consumed_quantity",
            "total_cogs": "total_cogs",
        }
        requested = (ordering or "sku").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"), "sku")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def variant_report_rows(self, variants):
        """Batched money fields for one page of report variants."""
        variant_ids = [variant.id for variant in variants]
        supplies_by_variant = defaultdict(list)
        for supply in self._received_supplies_queryset().filter(
            variant_id__in=variant_ids
        ).order_by("variant_id", "-supplied_at", "-id"):
            supplies_by_variant[supply.variant_id].append(supply)
        consumption_stats = self._consumption_stats_by_variant(variant_ids)
        configs = {
            pricing.variant_id: pricing
            for pricing in VariantPricing.objects.filter(variant_id__in=variant_ids)
        }
        rows = {}
        money = Decimal("0.01")
        for variant in variants:
            supplies = supplies_by_variant.get(variant.id, [])
            stats = consumption_stats.get(variant.id, {})
            remaining_quantity = sum(supply.remaining_quantity for supply in supplies)
            inventory_cost_value = sum(
                (
                    Decimal(supply.remaining_quantity)
                    * self.pricing_service.calculate_landed_unit_cost(supply)
                    for supply in supplies
                ),
                Decimal("0"),
            )
            average_remaining_cost = (
                inventory_cost_value / Decimal(remaining_quantity)
                if remaining_quantity
                else None
            )
            config = configs.get(variant.id)
            suggested_price = None
            if config is not None and supplies:
                basis = self.pricing_service.calculate_basis(config.cost_strategy, supplies)
                suggested_price = (
                    basis * (Decimal("1") + Decimal(config.expected_profit_percentage) / Decimal("100"))
                ).quantize(money)
            rows[variant.id] = {
                "variant_id": variant.id,
                "sku": variant.sku,
                "product_name": variant.product.name,
                "remaining_quantity": remaining_quantity,
                "inventory_cost_value": inventory_cost_value.quantize(money),
                "average_remaining_cost": (
                    average_remaining_cost.quantize(money)
                    if average_remaining_cost is not None
                    else None
                ),
                "total_consumed_quantity": stats.get("consumed_quantity", 0) or 0,
                "total_cogs": (stats.get("total_cogs") or Decimal("0")).quantize(money),
                "current_price": variant.price,
                "suggested_price": suggested_price,
            }
        return rows

    # ─────────────────────────── supply report ────────────────────────────

    def search_supplies_for_report(self, *, search=None, ordering=None):
        queryset = self._received_supplies_queryset().select_related(
            "variant__product", "warehouse"
        )
        if search:
            queryset = queryset.filter(
                Q(variant__sku__icontains=search)
                | Q(reference_number__icontains=search)
                | Q(invoice_number__icontains=search)
            )
        ordering_map = {
            "supplied_at": "supplied_at",
            "unit_buy_price": "unit_buy_price",
            "remaining_quantity": "remaining_quantity",
            "original_quantity": "quantity",
        }
        requested = (ordering or "-supplied_at").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"))
        if field is None:
            return queryset.order_by("-supplied_at", "-id")
        return queryset.order_by(f"-{field}" if descending else field, "-id")

    def serialize_supply_report_row(self, supply):
        landed_unit_cost = self.pricing_service.calculate_landed_unit_cost(supply)
        quantity = Decimal(supply.quantity)
        remaining_quantity = Decimal(supply.remaining_quantity)
        original_cost_value = landed_unit_cost * quantity
        remaining_cost_value = landed_unit_cost * remaining_quantity
        money = Decimal("0.01")
        return {
            "supply_id": supply.id,
            "variant": {
                "id": supply.variant_id,
                "sku": supply.variant.sku,
                "product_name": supply.variant.product.name,
            },
            "warehouse": {
                "id": supply.warehouse_id,
                "code": supply.warehouse.code,
                "name": supply.warehouse.name,
            },
            "original_quantity": supply.quantity,
            "remaining_quantity": supply.remaining_quantity,
            "consumed_quantity": supply.quantity - supply.remaining_quantity,
            "unit_buy_price": supply.unit_buy_price,
            "landed_unit_cost": landed_unit_cost.quantize(money),
            "original_cost_value": original_cost_value.quantize(money),
            "remaining_cost_value": remaining_cost_value.quantize(money),
            "consumed_cost_value": (original_cost_value - remaining_cost_value).quantize(money),
        }
