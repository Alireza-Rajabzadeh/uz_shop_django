import uuid

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, When
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from domains.catalog.models import Category
from domains.inventory.models import (
    InventoryStrategy,
    SerializedStock,
    SerializedStockStatus,
    Warehouse,
    WarehouseStatus,
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

    def search_variants(
        self,
        *,
        search=None,
        product=None,
        category=None,
        strategy_code=None,
        stock_state=None,
        has_reserved=None,
        ordering=None,
    ):
        from domains.catalog.models import ProductVariants

        primary_category = Category.objects.filter(
            products=OuterRef("product_id")
        ).order_by("id").values("name")[:1]
        queryset = ProductVariants.objects.select_related(
            "product", "inventory_strategy"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).annotate(primary_category_name=Subquery(primary_category))
        queryset = self.annotate_variant_summaries(queryset)
        reserved_normal = WarehouseStock.objects.filter(
            variant_id=OuterRef("pk")
        ).values("variant_id")
        reserved_serialized = SerializedStock.objects.filter(
            variant_id=OuterRef("pk"), reserved=True
        ).values("variant_id")
        default_stock = WarehouseStock.objects.filter(
            variant_id=OuterRef("pk"), warehouse__is_default=True
        )
        queryset = queryset.annotate(
            normal_reserved=Coalesce(
                Subquery(reserved_normal.annotate(value=Sum("reserved")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            serialized_reserved=Coalesce(
                Subquery(reserved_serialized.annotate(value=Count("id")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            min_stock=Coalesce(
                Subquery(default_stock.values("min_stock")[:1]),
                0,
                output_field=IntegerField(),
            ),
        ).annotate(
            reserved_item_count=Case(
                When(inventory_strategy__code="normal", then=F("normal_reserved")),
                default=F("serialized_reserved"),
                output_field=IntegerField(),
            )
        )
        if search:
            queryset = queryset.filter(Q(sku__icontains=search) | Q(product__name__icontains=search))
        if product is not None:
            queryset = queryset.filter(product_id=product)
        if category is not None:
            queryset = queryset.filter(product__categories__id=category).distinct()
        if strategy_code:
            queryset = queryset.filter(inventory_strategy__code=strategy_code)
        if has_reserved is not None:
            queryset = (
                queryset.filter(reserved_item_count__gt=0)
                if has_reserved
                else queryset.filter(reserved_item_count=0)
            )
        if stock_state == "in_stock":
            queryset = queryset.filter(available_item_count__gt=0)
        elif stock_state == "out_of_stock":
            queryset = queryset.filter(available_item_count=0)
        elif stock_state == "low_stock":
            queryset = queryset.filter(available_item_count__gt=0, min_stock__gt=0)
            queryset = queryset.filter(available_item_count__lte=F("min_stock"))
        ordering_map = {
            "id": "id",
            "sku": "sku",
            "product_name": "product__name",
            "category_name": "primary_category_name",
            "strategy": "inventory_strategy__code",
            "total": "total_item_count",
            "sellable": "sellable_item_count",
            "reserved": "reserved_item_count",
            "available": "available_item_count",
            "min_stock": "min_stock",
        }
        requested = (ordering or "sku").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"), "sku")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def serialize_variant_overview(self, variant, default_warehouse):
        primary_category = variant.product.categories.order_by("id").first()
        return {
            "variant": variant.id,
            "sku": variant.sku,
            "product_id": variant.product_id,
            "product_name": variant.product.name,
            "category_id": primary_category.id if primary_category else None,
            "category_name": primary_category.name if primary_category else None,
            "strategy": {
                "id": variant.inventory_strategy_id,
                "code": variant.inventory_strategy.code,
                "name": variant.inventory_strategy.name,
            },
            "total": variant.total_item_count,
            "sellable": variant.sellable_item_count,
            "reserved": variant.reserved_item_count,
            "available": variant.available_item_count,
            "min_stock": variant.min_stock,
            "low_stock": bool(
                variant.min_stock > 0
                and 0 < variant.available_item_count <= variant.min_stock
            ),
            "default_warehouse": self.serialize_warehouse(default_warehouse),
        }

    def search_warehouses(self, *, search=None, status=None, city=None, ordering=None):
        queryset = Warehouse.objects.select_related("status", "city__state__country")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        if status is not None:
            queryset = queryset.filter(status_id=status)
        if city is not None:
            queryset = queryset.filter(city_id=city)
        ordering_map = {
            "id": "id",
            "code": "code",
            "name": "name",
            "city_name": "city__name",
            "status_name": "status__name",
            "is_default": "is_default",
        }
        requested = (ordering or "-is_default").strip()
        descending = requested.startswith("-")
        field = ordering_map.get(requested.lstrip("-"), "is_default")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def get_warehouse(self, warehouse_id, *, lock=False):
        queryset = Warehouse.objects.select_related("status", "city__state__country")
        if lock:
            queryset = queryset.select_for_update()
        return queryset.filter(pk=warehouse_id).first()

    @transaction.atomic
    def create_warehouse(self, **values):
        # A status row provides a stable lock even while the warehouse table is empty.
        list(WarehouseStatus.objects.select_for_update().order_by().values_list("id", flat=True))
        list(Warehouse.objects.select_for_update().order_by().values_list("id", flat=True))
        values["is_default"] = not Warehouse.objects.exists() or values.get("is_default", False)
        if values["is_default"]:
            Warehouse.objects.filter(is_default=True).update(is_default=False)
        warehouse = Warehouse.objects.create(code=f"NEW-{uuid.uuid4().hex[:12]}", **values)
        warehouse.code = f"WH-{warehouse.id:05d}"
        try:
            warehouse.save(update_fields=["code"])
        except IntegrityError as exc:
            raise self.ValidationError({"code": [_('Could not generate a unique warehouse code.')]}) from exc
        return self.get_warehouse(warehouse.id)

    @transaction.atomic
    def update_warehouse(self, warehouse, **values):
        list(Warehouse.objects.select_for_update().order_by().values_list("id", flat=True))
        warehouse = self.get_warehouse(warehouse.id, lock=True)
        make_default = values.get("is_default") is True
        if values.get("is_default") is False and warehouse.is_default:
            if Warehouse.objects.exclude(pk=warehouse.pk).exists():
                raise self.ValidationError({
                    "is_default": [_('Switch another warehouse to default instead.')]
                })
            values["is_default"] = True
        if make_default:
            current_default = Warehouse.objects.filter(is_default=True).exclude(pk=warehouse.pk).first()
            if current_default and (
                current_default.stocks.filter(quantity__gt=0).exists()
                or current_default.serialized_stocks.exists()
            ):
                raise self.ValidationError({
                    "is_default": [_('The default warehouse cannot be changed while it contains stock.')]
                })
            Warehouse.objects.exclude(pk=warehouse.pk).filter(is_default=True).update(is_default=False)
        for field, value in values.items():
            setattr(warehouse, field, value)
        warehouse.save()
        return self.get_warehouse(warehouse.id)

    @transaction.atomic
    def delete_warehouse(self, warehouse):
        list(Warehouse.objects.select_for_update().order_by().values_list("id", flat=True))
        warehouse = self.get_warehouse(warehouse.id, lock=True)
        if warehouse.is_default:
            raise self.ValidationError({
                "is_default": [_('The default warehouse cannot be deleted. Switch another warehouse to default first.')]
            })
        try:
            warehouse.delete()
        except ProtectedError as exc:
            raise self.ValidationError({
                "warehouse": [_('This warehouse cannot be deleted while it contains stock.')]
            }) from exc

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
        min_stock = inventory.get("min_stock", stock.min_stock if stock else 0)
        if reserved > sellable or sellable > quantity:
            raise self.ValidationError({
                "inventory": [_('Inventory must satisfy 0 <= reserved <= sellable <= quantity.')]
            })
        WarehouseStock.objects.update_or_create(
            variant=variant,
            warehouse=warehouse,
            defaults={
                "quantity": quantity,
                "sellable": sellable,
                "reserved": reserved,
                "min_stock": min_stock,
            },
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
                changed_existing = []
                for item, serial_number in zip(serial_items, normalized_serials):
                    row_id = item.get("id")
                    if row_id is None:
                        continue
                    row = existing[row_id]
                    changed = row.serial_number != serial_number or row.sellable != item["on_sale"]
                    if changed and not self._is_editable(row):
                        raise self.ValidationError({
                            "serial_items": [_('Sold, reserved, or historical serialized rows cannot be edited.')]
                        })
                    if changed:
                        changed_existing.append((row, serial_number, item["on_sale"]))

                # Release current unique serial values before applying a valid swapped snapshot.
                for changed in changed_existing:
                    row = changed[0]
                    row.serial_number = f"__inventory_tmp_{row.id}_{uuid.uuid4().hex}"
                    row.save(update_fields=["serial_number"])

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
        from django.db.models import Sum
        from domains.inventory.models import InventorySupply

        summary = self.get_summary(variant)
        primary_category = variant.product.categories.order_by("id").first()
        strategy = {
            "id": variant.inventory_strategy_id,
            "code": variant.inventory_strategy.code,
            "name": variant.inventory_strategy.name,
        }
        context = {
            "sku": variant.sku,
            "product": {"id": variant.product_id, "name": variant.product.name},
            "category": {
                "id": primary_category.id if primary_category else None,
                "name": primary_category.name if primary_category else None,
            },
            "selections": [
                {
                    "attribute_id": selection.attribute_id,
                    "attribute_name": selection.attribute.name,
                    "option_id": selection.option_id,
                    "option_name": selection.option.name,
                }
                for selection in variant.selections.all()
            ],
        }
        total_supply_quantity = (
            InventorySupply.objects.filter(
                variant=variant
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        if variant.inventory_strategy.code == "normal":
            warehouse = self.get_default_warehouse()
            stock = variant.warehouse_stocks.filter(warehouse=warehouse).first()
            return {
                "variant_id": variant.id,
                **context,
                "strategy": strategy,
                **summary,
                "total_supply_quantity": total_supply_quantity,
                "inventory": {
                    "warehouse": self.serialize_warehouse(warehouse),
                    "quantity": stock.quantity if stock else 0,
                    "sellable": stock.sellable if stock else 0,
                    "reserved": stock.reserved if stock else 0,
                    "available": stock.available if stock else 0,
                    "min_stock": stock.min_stock if stock else 0,
                },
                "serial_items": None,
            }
        rows = variant.serialized_stocks.select_related("status", "warehouse").order_by("id")
        return {
            "variant_id": variant.id,
            **context,
            "strategy": strategy,
            **summary,
            "total_supply_quantity": total_supply_quantity,
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

    @transaction.atomic
    def adjust_variant_stock(self, variant, *, inventory=None, serial_items=None):
        variant = type(variant).objects.select_for_update().select_related(
            "inventory_strategy", "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).get(pk=variant.pk)
        strategy_code = variant.inventory_strategy.code
        self.apply_variant_inventory(
            variant,
            strategy_code=strategy_code,
            inventory=inventory,
            serial_items=serial_items,
            inventory_submitted=True,
        )
        return type(variant).objects.select_related(
            "inventory_strategy", "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).get(pk=variant.pk)

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

    @transaction.atomic
    def receive_normal_stock(self, *, variant, warehouse, quantity):
        # Additive receiving: increases quantity and sellable by the supplied
        # delta; reserved and remaining_quantity are never touched here.
        stock = WarehouseStock.objects.select_for_update().filter(
            variant=variant, warehouse=warehouse
        ).first()
        if stock is None:
            WarehouseStock.objects.create(
                variant=variant,
                warehouse=warehouse,
                quantity=quantity,
                sellable=quantity,
                reserved=0,
                min_stock=0,
            )
            return
        stock.quantity += quantity
        stock.sellable += quantity
        stock.save(update_fields=["quantity", "sellable"])

    @transaction.atomic
    def receive_serialized_stock(self, *, variant, warehouse, serial_numbers, supply):
        in_stock = SerializedStockStatus.objects.filter(code="in_stock").first()
        if in_stock is None:
            raise self.ValidationError({
                "serial_items": [_('Inventory setup is missing the in_stock serialized status.')]
            })
        normalized = [self.normalize_serial(value) for value in serial_numbers]
        if any(not value for value in normalized):
            raise self.ValidationError({
                "serial_items": [_('Serial number cannot be blank.')]
            })
        folded = [value.casefold() for value in normalized]
        if len(folded) != len(set(folded)):
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            })
        try:
            with transaction.atomic():
                SerializedStock.objects.bulk_create([
                    SerializedStock(
                        variant=variant,
                        warehouse=warehouse,
                        status=in_stock,
                        serial_number=value,
                        sellable=True,
                        reserved=False,
                        supply=supply,
                    )
                    for value in normalized
                ])
        except IntegrityError as exc:
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            }) from exc
