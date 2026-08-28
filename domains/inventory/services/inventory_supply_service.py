from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum
from domains.inventory.models import (
    InventorySupply,
    InventorySupplyConsumption,
    InventorySupplyCost,
    SerializedStock,
    WarehouseStock,
)
from domains.inventory.services.inventory_cost_service import InventoryCostService
from domains.inventory.services.inventory_service import InventoryService
from domains.order.models import OrderItem


class InventorySupplyService:
    # Purchase/cost history management for InventorySupply batches. Creating,
    # updating, and deleting supplies only records purchase/cost history;
    # physical inventory is touched exclusively by receive_supply().

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def __init__(self):
        self.cost_service = InventoryCostService()
        self.inventory_service = InventoryService()

    def _base_queryset(self, *, lock=False):
        # Single SUM annotation avoids per-row cost queries; remaining totals
        # mirror InventoryCostService formulas and are derived in
        # serialize_supply_row from persisted columns.
        queryset = InventorySupply.objects.select_related(
            "variant__product", "warehouse"
        ).annotate(
            extra_cost_total=Coalesce(
                Sum("costs__amount"),
                Decimal("0"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        )
        if lock:
            queryset = queryset.select_for_update()
        return queryset

    def search_supplies(
        self,
        *,
        search=None,
        variant_id=None,
        warehouse_id=None,
        date_from=None,
        date_to=None,
        has_remaining=None,
        received=None,
        ordering=None,
    ):
        queryset = self._base_queryset()

        if search:
            queryset = queryset.filter(
                Q(variant__sku__icontains=search)
                | Q(variant__product__name__icontains=search)
                | Q(reference_number__icontains=search)
                | Q(invoice_number__icontains=search)
            )
        if variant_id is not None:
            queryset = queryset.filter(variant_id=variant_id)
        if warehouse_id is not None:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        if date_from is not None:
            queryset = queryset.filter(supplied_at__gte=date_from)
        if date_to is not None:
            queryset = queryset.filter(supplied_at__lte=date_to)
        if has_remaining is not None:
            if has_remaining:
                queryset = queryset.filter(remaining_quantity__gt=0)
            else:
                queryset = queryset.filter(remaining_quantity=0)
        if received is not None:
            if received:
                queryset = queryset.filter(received_at__isnull=False)
            else:
                queryset = queryset.filter(received_at__isnull=True)

        ordering_map = {
            "supplied_at": "supplied_at",
            "created_at": "created_at",
            "quantity": "quantity",
            "remaining_quantity": "remaining_quantity",
            "unit_buy_price": "unit_buy_price",
        }
        requested = (ordering or "-supplied_at").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"))
        if field is None:
            return queryset.order_by("-supplied_at", "-id")
        return queryset.order_by(f"-{field}" if descending else field, "-id")

    def get_supply(self, supply_id, *, lock=False):
        queryset = self._base_queryset(lock=lock).prefetch_related("costs")
        return queryset.filter(pk=supply_id).first()

    @transaction.atomic
    def create_supply(
        self,
        *,
        variant,
        warehouse,
        quantity,
        unit_buy_price,
        supplied_at,
        reference_number="",
        invoice_number="",
        notes="",
        costs=None,
    ):
        validated_costs = self._validate_cost_rows(costs or [])
        supply = InventorySupply.objects.create(
            variant=variant,
            warehouse=warehouse,
            quantity=quantity,
            unit_buy_price=unit_buy_price,
            supplied_at=supplied_at,
            reference_number=reference_number,
            invoice_number=invoice_number,
            notes=notes,
        )
        InventorySupplyCost.objects.bulk_create(
            [InventorySupplyCost(supply=supply, **row) for row in validated_costs]
        )
        return self.get_supply(supply.id)

    @transaction.atomic
    def update_supply(self, supply, **values):
        supply = (
            InventorySupply.objects.select_for_update()
            .select_related("variant__product", "warehouse", "variant__inventory_strategy")
            .prefetch_related("costs")
            .get(pk=supply.pk)
        )
        cost_rows = values.pop("costs", None)
        if supply.received_at is not None:
            blocked = []
            if "variant" in values and values["variant"].pk != supply.variant_id:
                blocked.append("variant")
            if "warehouse" in values and values["warehouse"].pk != supply.warehouse_id:
                blocked.append("warehouse")
            if "quantity" in values and values["quantity"] != supply.quantity:
                blocked.append("quantity")
            if blocked:
                raise self.ValidationError({
                    "receive": [
                        _('Received supplies cannot change variant, warehouse, or quantity.')
                    ]
                })
            values.pop("variant", None)
            values.pop("warehouse", None)
            values.pop("quantity", None)
        if "quantity" in values:
            new_quantity = values.pop("quantity")
            consumed = (
                supply.remaining_quantity is not None
                and supply.remaining_quantity != supply.quantity
            )
            if consumed and new_quantity != supply.quantity:
                raise self.ValidationError({
                    "quantity": [
                        _('Quantity cannot change because this supply has already been consumed.')
                    ]
                })
            if new_quantity != supply.quantity:
                values["remaining_quantity"] = new_quantity
                values["quantity"] = new_quantity
        for field, value in values.items():
            setattr(supply, field, value)
        supply.save()
        if cost_rows is not None:
            validated_costs = self._validate_cost_rows(cost_rows)
            supply.costs.all().delete()
            InventorySupplyCost.objects.bulk_create(
                [InventorySupplyCost(supply=supply, **row) for row in validated_costs]
            )
        return self.get_supply(supply.id)

    @transaction.atomic
    def delete_supply(self, supply):
        supply = InventorySupply.objects.select_for_update().get(pk=supply.pk)
        if supply.received_at is not None:
            raise self.ValidationError({
                "supply": [_('Received supplies cannot be deleted.')]
            })
        if supply.remaining_quantity is not None and supply.remaining_quantity != supply.quantity:
            raise self.ValidationError({
                "supply": [_('Supply has already been consumed and cannot be deleted.')]
            })
        supply.delete()

    @transaction.atomic
    def receive_supply(self, supply, *, serial_items=None):
        # Receiving moves a recorded purchase batch into physical inventory.
        # It is additive, one-time only, and never changes remaining_quantity;
        # FIFO consumption will consume cost layers in a later step.
        supply = (
            InventorySupply.objects.select_for_update()
            .select_related("variant__inventory_strategy")
            .get(pk=supply.pk)
        )
        if supply.received_at is not None:
            raise self.ValidationError({
                "receive": [_('This supply has already been received.')]
            })
        strategy_code = supply.variant.inventory_strategy.code
        try:
            if strategy_code == "normal":
                if serial_items:
                    raise self.ValidationError({
                        "serial_items": [_('Serial items are only accepted for serialized inventory.')]
                    })
                self.inventory_service.receive_normal_stock(
                    variant=supply.variant,
                    warehouse=supply.warehouse,
                    quantity=supply.quantity,
                )
            else:
                # Serial items are added later through the inventory UI.
                # Receiving just marks the supply as confirmed.
                pass
        except InventoryService.ValidationError as exc:
            # Normalize the stock service's errors into this service's contract.
            if isinstance(exc, self.ValidationError):
                raise exc
            raise self.ValidationError(exc.errors) from exc
        supply.received_at = timezone.now()
        supply.save(update_fields=["received_at"])
        return self.get_supply(supply.id)

    @transaction.atomic
    def consume_order_item(self, order_item):
        # Consume supply cost layers for a finalized sale. Called from
        # OrderService.consume_reservations (payment approval), never during
        # cart/reservation/pending stages. Idempotent per order item.
        order_item = (
            OrderItem.objects.select_for_update()
            .select_related("inventory_strategy")
            .get(pk=order_item.pk)
        )
        if order_item.supply_consumptions.exists():
            raise self.ValidationError({
                "order_item": [
                    _('This order item has already consumed its supply layers.')
                ]
            })
        if order_item.variant_id is None:
            return []
        reservations = list(order_item.reservations.all())
        normal_ids = [r.inventory_id for r in reservations if r.inventory_type == "warehouse_stock"]
        serialized_ids = [r.inventory_id for r in reservations if r.inventory_type == "serialized_stock"]
        if order_item.inventory_strategy.code == "normal":
            return self._consume_normal_layers(order_item, normal_ids)
        return self._consume_serialized_layers(order_item, serialized_ids)

    def _consume_normal_layers(self, order_item, reservation_ids):
        stock_rows = WarehouseStock.objects.filter(id__in=reservation_ids)
        needs = {}
        quantities = {r.inventory_id: r.quantity for r in order_item.reservations.all()}
        for stock in stock_rows:
            needs[stock.warehouse_id] = (
                needs.get(stock.warehouse_id, 0) + quantities.get(stock.id, 0)
            )
        consumptions = []
        for warehouse_id, need in needs.items():
            consumptions.extend(
                self._consume_fifo(
                    order_item, variant_id=order_item.variant_id,
                    warehouse_id=warehouse_id, quantity=need,
                )
            )
        return consumptions

    def _consume_fifo(self, order_item, *, variant_id, warehouse_id, quantity):
        supplies = list(
            InventorySupply.objects.select_for_update()
            .filter(
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                received_at__isnull=False,
                remaining_quantity__gt=0,
            )
            .order_by("supplied_at", "id")
        )
        # Stock that never entered through the supply system (development
        # fixtures or legacy rows) is sold without COGS attribution.
        has_any_layer = InventorySupply.objects.filter(
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            received_at__isnull=False,
        ).exists()
        if not has_any_layer:
            return []
        available = sum(supply.remaining_quantity for supply in supplies)
        if available < quantity:
            raise self.ValidationError({
                "supply": [
                    _('Supplies do not cover %(needed)s units for this sale.')
                    % {"needed": quantity}
                ]
            })
        consumptions = []
        for supply in supplies:
            if quantity == 0:
                break
            take = min(quantity, supply.remaining_quantity)
            consumptions.append(self._create_consumption(order_item, supply, take))
            supply.remaining_quantity -= take
            supply.save(update_fields=["remaining_quantity"])
            quantity -= take
        return consumptions

    def _consume_serialized_layers(self, order_item, serialized_stock_ids):
        # NOTE: no select_related here -- FOR UPDATE cannot be applied to the
        # nullable side of an outer join on PostgreSQL; supplies are locked
        # explicitly below instead.
        rows = list(
            SerializedStock.objects.select_for_update()
            .filter(id__in=serialized_stock_ids)
        )
        counts_by_supply = {}
        for row in rows:
            # Serialized units received before supply linkage existed cannot
            # be attributed to a cost layer and are skipped.
            if row.supply_id is None:
                continue
            counts_by_supply[row.supply_id] = counts_by_supply.get(row.supply_id, 0) + 1
        consumptions = []
        for supply_id, count in sorted(counts_by_supply.items()):
            supply = InventorySupply.objects.select_for_update().get(pk=supply_id)
            if supply.remaining_quantity < count:
                raise self.ValidationError({
                    "supply": [
                        _('Supply %(reference)s does not cover %(needed)s consumed units.')
                        % {"reference": supply.reference_number or supply.id, "needed": count}
                    ]
                })
            consumptions.append(self._create_consumption(order_item, supply, count))
            supply.remaining_quantity -= count
            supply.save(update_fields=["remaining_quantity"])
        return consumptions

    def _create_consumption(self, order_item, supply, quantity):
        landed_unit_cost = self.cost_service.get_landed_unit_cost(supply)
        return InventorySupplyConsumption.objects.create(
            supply=supply,
            order_item=order_item,
            quantity=quantity,
            unit_cost=landed_unit_cost.quantize(Decimal("0.01")),
        )

    @transaction.atomic
    def reverse_order_item_consumption(self, order_item, *, quantity=None):
        # Restore consumed cost layers for a cancelled or returned order item.
        # Consumption records are the source of truth: quantities go back to
        # the exact supplies they came from and FIFO is never recalculated.
        #
        # Partial reversals consume the reversible pool in a deterministic
        # order: most recently consumed layer first (created_at DESC, id DESC).
        order_item = OrderItem.objects.select_for_update().get(pk=order_item.pk)
        records = list(
            order_item.supply_consumptions.select_for_update()
            .select_related("supply")
            .order_by("-created_at", "-id")
        )
        reversible = {
            record.id: record.quantity - record.reversed_quantity
            for record in records
        }
        total_reversible = sum(reversible.values())
        if quantity is None:
            target = total_reversible
        else:
            if quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Reversal quantity must be greater than zero.')]
                })
            if quantity > total_reversible:
                raise self.ValidationError({
                    "quantity": [
                        _('Only %(available)s consumed units are reversible.')
                        % {"available": total_reversible}
                    ]
                })
            target = quantity

        reversed_total = 0
        for record in records:
            if reversed_total >= target:
                break
            take = min(reversible[record.id], target - reversed_total)
            if take == 0:
                continue
            # record.supply is already row-locked by the joined select_for_update.
            supply = record.supply
            supply.remaining_quantity += take
            supply.save(update_fields=["remaining_quantity"])
            record.reversed_quantity += take
            record.save(update_fields=["reversed_quantity"])
            reversed_total += take
        return reversed_total

    def _validate_cost_rows(self, cost_rows):
        supported = {member.value for member in InventorySupplyCostTypeEnum}
        validated = []
        for row in cost_rows:
            code = row.get("type")
            if code not in supported:
                raise self.ValidationError({"costs": [_('Unsupported supply cost type.')]})
            try:
                amount = Decimal(str(row.get("amount")))
            except (InvalidOperation, ValueError):
                raise self.ValidationError({"costs": [_('A valid amount is required.')]})
            if amount < 0:
                raise self.ValidationError({
                    "costs": [_('Amount must be greater than or equal to zero.')]
                })
            validated.append({
                "type": code,
                "amount": amount,
                "description": row.get("description") or "",
            })
        return validated

    def serialize_supply_row(self, supply):
        variant = supply.variant
        warehouse = supply.warehouse
        unit_buy_price = Decimal(supply.unit_buy_price)
        base_cost_total = unit_buy_price * Decimal(supply.quantity)
        extra_cost_total = Decimal(supply.extra_cost_total)
        landed_cost_total = base_cost_total + extra_cost_total
        return {
            "id": supply.id,
            "variant": {
                "id": variant.id,
                "sku": variant.sku,
                "product_name": variant.product.name,
            },
            "warehouse": {"id": warehouse.id, "code": warehouse.code, "name": warehouse.name},
            "quantity": supply.quantity,
            "remaining_quantity": supply.remaining_quantity,
            "unit_buy_price": unit_buy_price,
            "base_cost_total": base_cost_total,
            "extra_cost_total": extra_cost_total,
            "landed_cost_total": landed_cost_total,
            "landed_unit_cost": landed_cost_total / Decimal(supply.quantity),
            "supplied_at": supply.supplied_at,
            "received_at": supply.received_at,
            "is_received": supply.received_at is not None,
            "reference_number": supply.reference_number,
            "invoice_number": supply.invoice_number,
            "created_at": supply.created_at,
            "updated_at": supply.updated_at,
        }

    def serialize_supply_detail(self, supply):
        row = self.serialize_supply_row(supply)
        # Detail totals come from the authoritative InventoryCostService.
        row.update(self.cost_service.get_cost_summary(supply))
        row.update({
            "notes": supply.notes,
            "costs": [
                {
                    "id": cost.id,
                    "type": cost.type,
                    "amount": cost.amount,
                    "description": cost.description,
                }
                for cost in supply.costs.all()
            ],
        })
        return row
