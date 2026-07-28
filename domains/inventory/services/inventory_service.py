from django.db import IntegrityError, transaction
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from domains.inventory.models import (
    InventoryStrategy,
    SerializedStock,
    SerializedStockStatus,
    Warehouse,
    WarehouseStock,
)


class InventoryService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def get_strategies(self):
        return InventoryStrategy.objects.filter(
            code__in=("normal", "serialized")
        ).order_by("id")

    def annotate_variant_summaries(self, queryset):
        normal = WarehouseStock.objects.filter(variant_id=OuterRef("pk")).values("variant_id")
        serialized = SerializedStock.objects.filter(variant_id=OuterRef("pk")).values("variant_id")
        return queryset.annotate(
            normal_total=Coalesce(
                Subquery(normal.annotate(value=Sum("quantity")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            normal_sellable=Coalesce(
                Subquery(normal.annotate(value=Sum("sellable")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            normal_available=Coalesce(
                Subquery(
                    normal.annotate(value=Sum(F("sellable") - F("reserved"))).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
            serialized_total=Coalesce(
                Subquery(serialized.annotate(value=Count("id")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            serialized_sellable=Coalesce(
                Subquery(
                    serialized.annotate(value=Count("id", filter=Q(sellable=True))).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
            serialized_available=Coalesce(
                Subquery(
                    serialized.annotate(
                        value=Count(
                            "id",
                            filter=Q(status__code="in_stock", sellable=True, reserved=False),
                        )
                    ).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
        ).annotate(
            total_item_count=Case(
                When(inventory_strategy__code="normal", then=F("normal_total")),
                default=F("serialized_total"),
                output_field=IntegerField(),
            ),
            sellable_item_count=Case(
                When(inventory_strategy__code="normal", then=F("normal_sellable")),
                default=F("serialized_sellable"),
                output_field=IntegerField(),
            ),
            available_item_count=Case(
                When(inventory_strategy__code="normal", then=F("normal_available")),
                default=F("serialized_available"),
                output_field=IntegerField(),
            ),
        )

    def get_default_warehouse(self, *, lock=False):
        queryset = Warehouse.objects.select_related("status")
        if lock:
            queryset = queryset.select_for_update()
        warehouses = list(queryset.filter(is_default=True)[:2])
        if len(warehouses) != 1:
            raise self.ValidationError({
                "inventory": [_('Inventory setup requires exactly one default warehouse.')]
            })
        return warehouses[0]

    @transaction.atomic
    def apply_variant_inventory(
        self,
        variant,
        *,
        strategy_code,
        inventory=None,
        serial_items=None,
        inventory_submitted=False,
    ):
        strategy = InventoryStrategy.objects.filter(code=strategy_code).first()
        if strategy is None or strategy_code not in {"normal", "serialized"}:
            raise self.ValidationError({
                "inventory_strategy_code": [_('Choose either normal or serialized.')]
            })

        current_code = variant.inventory_strategy.code
        if current_code != strategy_code:
            self._validate_empty_for_transition(variant, current_code)
            variant.inventory_strategy = strategy
            variant.save(update_fields=["inventory_strategy"])

        if not inventory_submitted:
            return
        warehouse = self.get_default_warehouse(lock=True)
        if strategy_code == "normal":
            self._apply_normal(variant, warehouse, inventory)
        else:
            self._apply_serialized_snapshot(variant, warehouse, serial_items)

    def _validate_empty_for_transition(self, variant, current_code):
        if current_code == "normal":
            stocks = variant.warehouse_stocks.select_for_update()
            has_inventory = stocks.filter(quantity__gt=0).exists()
            if not has_inventory:
                stocks.delete()
        else:
            has_inventory = variant.serialized_stocks.exists()
        if has_inventory:
            raise self.ValidationError({
                "inventory_strategy_code": [
                    _('Inventory strategy cannot change while the current strategy has stock.')
                ]
            })

    def _apply_normal(self, variant, warehouse, inventory):
        if inventory is None:
            raise self.ValidationError({"inventory": [_('This field is required for normal inventory.')]})
        stock = WarehouseStock.objects.select_for_update().filter(
            variant=variant, warehouse=warehouse
        ).first()
        reserved = stock.reserved if stock else 0
        quantity = inventory["quantity"]
        sellable = inventory["sellable"]
        if reserved > sellable or sellable > quantity:
            raise self.ValidationError({
                "inventory": [_('Inventory must satisfy 0 <= reserved <= sellable <= quantity.')]
            })
        WarehouseStock.objects.update_or_create(
            variant=variant,
            warehouse=warehouse,
            defaults={"quantity": quantity, "sellable": sellable, "reserved": reserved},
        )

    def _apply_serialized_snapshot(self, variant, warehouse, serial_items):
        if serial_items is None:
            raise self.ValidationError({
                "serial_items": [_('This field is required for serialized inventory.')]
            })
        existing = {
            row.id: row
            for row in SerializedStock.objects.select_for_update().select_related("status").filter(
                variant=variant
            )
        }
        supplied_ids = [item["id"] for item in serial_items if item.get("id") is not None]
        if len(supplied_ids) != len(set(supplied_ids)):
            raise self.ValidationError({"serial_items": [_('Each serialized row can only appear once.')]})
        if set(supplied_ids) - set(existing):
            raise self.ValidationError({
                "serial_items": [_('One or more serialized row IDs do not belong to this variant.')]
            })

        omitted = [row for row_id, row in existing.items() if row_id not in supplied_ids]
        protected_omitted = [row for row in omitted if not self._is_editable(row)]
        if protected_omitted:
            raise self.ValidationError({
                "serial_items": [_('Sold, reserved, or historical serialized rows cannot be deleted.')]
            })

        normalized_serials = [self.normalize_serial(item["serial_number"]) for item in serial_items]
        if any(not value for value in normalized_serials):
            raise self.ValidationError({"serial_items": [_('Serial number cannot be blank.')]})
        folded = [value.casefold() for value in normalized_serials]
        if len(folded) != len(set(folded)):
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            })

        in_stock = SerializedStockStatus.objects.filter(code="in_stock").first()
        if in_stock is None:
            raise self.ValidationError({
                "serial_items": [_('Inventory setup is missing the in_stock serialized status.')]
            })

        try:
            with transaction.atomic():
                for row in omitted:
                    row.delete()
                for item, serial_number in zip(serial_items, normalized_serials):
                    row_id = item.get("id")
                    if row_id is None:
                        SerializedStock.objects.create(
                            variant=variant,
                            warehouse=warehouse,
                            status=in_stock,
                            serial_number=serial_number,
                            sellable=item["on_sale"],
                            reserved=False,
                        )
                        continue
                    row = existing[row_id]
                    changed = row.serial_number != serial_number or row.sellable != item["on_sale"]
                    if changed and not self._is_editable(row):
                        raise self.ValidationError({
                            "serial_items": [_('Sold, reserved, or historical serialized rows cannot be edited.')]
                        })
                    if changed:
                        row.serial_number = serial_number
                        row.sellable = item["on_sale"]
                        row.save(update_fields=["serial_number", "sellable"])
        except IntegrityError as exc:
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            }) from exc

    @staticmethod
    def normalize_serial(value):
        return " ".join(value.split())

    @staticmethod
    def _is_editable(row):
        return row.status.code == "in_stock" and not row.reserved

    def get_summary(self, variant):
        if variant.inventory_strategy.code == "normal":
            rows = list(variant.warehouse_stocks.all())
            return {
                "total_item_count": sum(row.quantity for row in rows),
                "sellable_item_count": sum(row.sellable for row in rows),
                "available_item_count": sum(row.sellable - row.reserved for row in rows),
            }
        rows = list(variant.serialized_stocks.all())
        return {
            "total_item_count": len(rows),
            "sellable_item_count": sum(row.sellable for row in rows),
            "available_item_count": sum(
                row.status.code == "in_stock" and row.sellable and not row.reserved
                for row in rows
            ),
        }

    def get_variant_details(self, variant):
        summary = self.get_summary(variant)
        strategy = {
            "id": variant.inventory_strategy_id,
            "code": variant.inventory_strategy.code,
            "name": variant.inventory_strategy.name,
        }
        if variant.inventory_strategy.code == "normal":
            warehouse = self.get_default_warehouse()
            stock = variant.warehouse_stocks.filter(warehouse=warehouse).first()
            return {
                "variant_id": variant.id,
                "strategy": strategy,
                **summary,
                "inventory": {
                    "warehouse": self.serialize_warehouse(warehouse),
                    "quantity": stock.quantity if stock else 0,
                    "sellable": stock.sellable if stock else 0,
                    "reserved": stock.reserved if stock else 0,
                    "available": stock.available if stock else 0,
                },
                "serial_items": None,
            }
        rows = variant.serialized_stocks.select_related("status", "warehouse").order_by("id")
        return {
            "variant_id": variant.id,
            "strategy": strategy,
            **summary,
            "inventory": None,
            "serial_items": [
                {
                    "id": row.id,
                    "serial_number": row.serial_number,
                    "on_sale": row.sellable,
                    "reserved": row.reserved,
                    "status": {"code": row.status.code, "name": row.status.name},
                    "warehouse": self.serialize_warehouse(row.warehouse),
                    "editable": self._is_editable(row),
                }
                for row in rows
            ],
        }

    @staticmethod
    def serialize_warehouse(warehouse):
        return {
            "id": warehouse.id,
            "code": warehouse.code,
            "name": warehouse.name,
            "status": warehouse.status.name,
        }

    def validate_variant_deletion(self, variant):
        stocks = variant.warehouse_stocks.all()
        has_normal_stock = stocks.filter(quantity__gt=0).exists()
        has_serialized_stock = variant.serialized_stocks.exists()
        if has_normal_stock or has_serialized_stock:
            raise self.ValidationError({
                "inventory": [_('A variant with stock cannot be deleted.')]
            })
        stocks.delete()
