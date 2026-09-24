import uuid

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _

from domains.catalog.models import Category
from domains.inventory.enums.InventoryUnitStateEnum import InventoryUnitStateEnum
from domains.inventory.models import (
    Inventory,
    InventoryAttributeDefinition,
    InventoryTransfer,
    InventoryUnit,
    InventoryUnitAttribute,
    Warehouse,
    WarehouseStatus,
)

_VALID_TRANSITIONS = {
    InventoryUnitStateEnum.IN_STOCK.value: {
        InventoryUnitStateEnum.RESERVED.value,
        InventoryUnitStateEnum.SOLD.value,
        InventoryUnitStateEnum.DAMAGED.value,
        InventoryUnitStateEnum.LOST.value,
    },
    InventoryUnitStateEnum.RESERVED.value: {
        InventoryUnitStateEnum.IN_STOCK.value,
        InventoryUnitStateEnum.SOLD.value,
    },
    InventoryUnitStateEnum.RETURNED.value: {
        InventoryUnitStateEnum.IN_STOCK.value,
    },
}


class InventoryService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def search_variants(
        self,
        *,
        search=None,
        product=None,
        category=None,
        stock_state=None,
        has_reserved=None,
        ordering=None,
    ):
        from domains.catalog.models import ProductVariants

        primary_category = Category.objects.filter(
            products=OuterRef("product_id")
        ).order_by("id").values("name")[:1]
        queryset = ProductVariants.objects.select_related(
            "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).annotate(primary_category_name=Subquery(primary_category))
        queryset = self.annotate_variant_summaries(queryset)
        if search:
            queryset = queryset.filter(Q(sku__icontains=search) | Q(product__name__icontains=search))
        if product is not None:
            queryset = queryset.filter(product_id=product)
        if category is not None:
            queryset = queryset.filter(product__categories__id=category).distinct()
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
        inv = Inventory.objects.filter(variant=variant, warehouse=default_warehouse).first()
        min_stock = inv.min_stock if inv else 0
        inv_type = self._detect_inventory_type(variant)
        strategy = {"id": 1, "code": "normal", "name": "Normal"} if inv_type == "normal" else {"id": 2, "code": "serialized", "name": "Serialized"}
        return {
            "variant": variant.id,
            "sku": variant.sku,
            "product_id": variant.product_id,
            "product_name": variant.product.name,
            "category_id": primary_category.id if primary_category else None,
            "category_name": primary_category.name if primary_category else None,
            "strategy": strategy,
            "total": variant.total_item_count,
            "sellable": variant.sellable_item_count,
            "reserved": variant.reserved_item_count,
            "available": variant.available_item_count,
            "min_stock": min_stock,
            "low_stock": bool(
                min_stock > 0
                and 0 < variant.available_item_count <= min_stock
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
        list(WarehouseStatus.objects.select_for_update().order_by().values_list("id", flat=True))
        list(Warehouse.objects.select_for_update().order_by().values_list("id", flat=True))
        business = values.get("business")
        values["is_default"] = not Warehouse.objects.filter(business=business).exists() or values.get("is_default", False)
        if values["is_default"]:
            Warehouse.objects.filter(business=business, is_default=True).update(is_default=False)
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
        business = warehouse.business
        make_default = values.get("is_default") is True
        if values.get("is_default") is False and warehouse.is_default:
            if Warehouse.objects.filter(business=business).exclude(pk=warehouse.pk).exists():
                raise self.ValidationError({
                    "is_default": [_('Switch another warehouse to default instead.')]
                })
            values["is_default"] = True
        if make_default:
            current_default = Warehouse.objects.filter(business=business, is_default=True).exclude(pk=warehouse.pk).first()
            if current_default and Inventory.objects.filter(
                warehouse=current_default, quantity__gt=0
            ).exists():
                raise self.ValidationError({
                    "is_default": [_('The default warehouse cannot be changed while it contains stock.')]
                })
            Warehouse.objects.filter(business=business).exclude(pk=warehouse.pk).filter(is_default=True).update(is_default=False)
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
        inventory_sub = Inventory.objects.filter(variant_id=OuterRef("pk")).values("variant_id")
        unit_sub = InventoryUnit.objects.filter(
            inventory__variant_id=OuterRef("pk")
        ).values("inventory__variant_id")
        return queryset.annotate(
            inv_quantity=Coalesce(
                Subquery(inventory_sub.annotate(value=Sum("quantity")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            inv_sellable=Coalesce(
                Subquery(inventory_sub.annotate(value=Sum("sellable")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            inv_reserved=Coalesce(
                Subquery(inventory_sub.annotate(value=Sum("reserved")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            unit_total=Coalesce(
                Subquery(unit_sub.annotate(value=Count("inventory__variant_id")).values("value")[:1]),
                0,
                output_field=IntegerField(),
            ),
            unit_sellable=Coalesce(
                Subquery(
                    unit_sub.filter(
                        inventory__variant_id=OuterRef("pk"),
                        state=InventoryUnitStateEnum.IN_STOCK.value,
                    ).annotate(value=Count("inventory__variant_id")).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
            unit_reserved=Coalesce(
                Subquery(
                    unit_sub.filter(
                        inventory__variant_id=OuterRef("pk"),
                        state=InventoryUnitStateEnum.RESERVED.value,
                    ).annotate(value=Count("inventory__variant_id")).values("value")[:1]
                ),
                0,
                output_field=IntegerField(),
            ),
        ).annotate(
            total_item_count=F("inv_quantity") + F("unit_total"),
            sellable_item_count=F("inv_sellable") + F("unit_sellable"),
            available_item_count=(F("inv_sellable") - F("inv_reserved")) + F("unit_sellable"),
            reserved_item_count=F("inv_reserved") + F("unit_reserved"),
            min_stock=Coalesce(
                Subquery(
                    Inventory.objects.filter(
                        variant_id=OuterRef("pk"), warehouse__is_default=True
                    ).values("variant_id").annotate(value=Sum("min_stock")).values("value")[:1]
                ),
                0,
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
        inventory=None,
        serial_items=None,
        inventory_submitted=False,
    ):
        if not inventory_submitted:
            return
        has_serialized = InventoryUnit.objects.filter(inventory__variant=variant).exists()
        if has_serialized or serial_items is not None:
            self._apply_serialized_snapshot(variant, serial_items)
        else:
            warehouse = self.get_default_warehouse(lock=True)
            self._apply_normal(variant, warehouse, inventory)

    def _apply_normal(self, variant, warehouse, inventory):
        if inventory is None:
            raise self.ValidationError({"inventory": [_('This field is required for normal inventory.')]})
        inv = Inventory.objects.select_for_update().filter(
            variant=variant, warehouse=warehouse
        ).first()
        reserved = inv.reserved if inv else 0
        quantity = inventory["quantity"]
        sellable = inventory["sellable"]
        min_stock = inventory.get("min_stock", inv.min_stock if inv else 0)
        if reserved > sellable or sellable > quantity:
            raise self.ValidationError({
                "inventory": [_('Inventory must satisfy 0 <= reserved <= sellable <= quantity.')]
            })
        if inv is None:
            from domains.business.models import BusinessProfile
            business = BusinessProfile.objects.get(id=1)
            inv = Inventory.objects.create(
                business=business,
                warehouse=warehouse,
                variant=variant,
                quantity=quantity,
                sellable=sellable,
                reserved=reserved,
                min_stock=min_stock,
            )
        else:
            inv.quantity = quantity
            inv.sellable = sellable
            inv.reserved = reserved
            inv.min_stock = min_stock
            inv.save(update_fields=["quantity", "sellable", "reserved", "min_stock"])

    def _apply_serialized_snapshot(self, variant, serial_items):
        if serial_items is None:
            raise self.ValidationError({
                "serial_items": [_('This field is required for serialized inventory.')]
            })
        inventory = Inventory.objects.filter(variant=variant).first()
        if inventory is None:
            from domains.business.models import BusinessProfile
            business = BusinessProfile.objects.get(id=1)
            warehouse = self.get_default_warehouse()
            inventory = Inventory.objects.create(
                business=business,
                warehouse=warehouse,
                variant=variant,
                quantity=0,
                sellable=0,
                reserved=0,
            )
        serial_attr_def = InventoryAttributeDefinition.objects.filter(code="serial_number").first()
        if serial_attr_def is None:
            raise self.ValidationError({
                "serial_items": [_('Inventory setup is missing the serial_number attribute definition.')]
            })
        existing = {
            unit.id: unit
            for unit in InventoryUnit.objects.select_for_update().filter(inventory=inventory)
        }
        existing_attrs = {
            a.inventory_unit_id: a
            for a in InventoryUnitAttribute.objects.filter(
                inventory_unit_id__in=list(existing.keys()),
                attribute_definition=serial_attr_def,
            )
        }
        supplied_ids = [item["id"] for item in serial_items if item.get("id") is not None]
        if len(supplied_ids) != len(set(supplied_ids)):
            raise self.ValidationError({"serial_items": [_('Each serialized row can only appear once.')]})
        if set(supplied_ids) - set(existing):
            raise self.ValidationError({
                "serial_items": [_('One or more serialized row IDs do not belong to this variant.')]
            })

        omitted = [unit for unit_id, unit in existing.items() if unit_id not in supplied_ids]
        protected_omitted = [unit for unit in omitted if not self._is_editable(unit)]
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
        existing_unit_ids = list(existing.keys())
        existing_serials = set(
            InventoryUnitAttribute.objects.filter(
                attribute_definition=serial_attr_def,
                inventory_unit_id__in=existing_unit_ids,
            ).values_list("value", flat=True)
        )
        global_serials = set(
            a.value.casefold()
            for a in InventoryUnitAttribute.objects.filter(
                attribute_definition=serial_attr_def,
            ).exclude(inventory_unit_id__in=existing_unit_ids)
        )
        for sn in folded:
            if sn in global_serials:
                raise self.ValidationError({
                    "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
                })

        try:
            with transaction.atomic():
                for unit in omitted:
                    InventoryUnitAttribute.objects.filter(inventory_unit=unit).delete()
                    unit.delete()
                changed_existing = []
                for item, serial_number in zip(serial_items, normalized_serials):
                    row_id = item.get("id")
                    if row_id is None:
                        continue
                    unit = existing[row_id]
                    attr = existing_attrs.get(row_id)
                    old_serial = attr.value if attr else ""
                    on_sale = item["on_sale"]
                    desired_state = InventoryUnitStateEnum.IN_STOCK.value if on_sale else InventoryUnitStateEnum.RESERVED.value
                    changed = old_serial != serial_number or unit.state != desired_state
                    if changed and not self._is_editable(unit):
                        raise self.ValidationError({
                            "serial_items": [_('Sold, reserved, or historical serialized rows cannot be edited.')]
                        })
                    if changed:
                        changed_existing.append((unit, serial_number, desired_state))

                for changed in changed_existing:
                    unit = changed[0]
                    InventoryUnitAttribute.objects.filter(
                        inventory_unit=unit, attribute_definition=serial_attr_def
                    ).update(value=f"__inventory_tmp_{unit.id}_{uuid.uuid4().hex}")

                for item, serial_number in zip(serial_items, normalized_serials):
                    row_id = item.get("id")
                    on_sale = item["on_sale"]
                    desired_state = InventoryUnitStateEnum.IN_STOCK.value if on_sale else InventoryUnitStateEnum.RESERVED.value
                    if row_id is None:
                        new_unit = InventoryUnit.objects.create(
                            inventory=inventory,
                            state=desired_state,
                        )
                        InventoryUnitAttribute.objects.create(
                            inventory_unit=new_unit,
                            attribute_definition=serial_attr_def,
                            value=serial_number,
                        )
                        continue
                    unit = existing[row_id]
                    unit.state = desired_state
                    unit.save(update_fields=["state"])
                    attr = existing_attrs.get(row_id)
                    if attr:
                        attr.value = serial_number
                        attr.save(update_fields=["value"])
                    else:
                        InventoryUnitAttribute.objects.create(
                            inventory_unit=unit,
                            attribute_definition=serial_attr_def,
                            value=serial_number,
                        )
        except IntegrityError as exc:
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            }) from exc
        self._sync_inventory_summary(inventory)

    @staticmethod
    def normalize_serial(value):
        return " ".join(value.split())

    @staticmethod
    def _is_editable(unit):
        return unit.state == InventoryUnitStateEnum.IN_STOCK.value

    def _detect_inventory_type(self, variant):
        if InventoryUnit.objects.filter(inventory__variant=variant).exists():
            return "serialized"
        return "normal"

    def _unit_queryset(self, variant, business=None):
        units = InventoryUnit.objects.filter(inventory__variant=variant)
        if business is not None:
            units = units.filter(inventory__business=business)
        return units

    def _normal_totals(self, variant, business=None):
        """Sum a variant's normal stock rows, optionally limited to one business."""
        from django.db.models import Sum

        rows = Inventory.objects.filter(variant=variant)
        if business is not None:
            rows = rows.filter(business=business)
        totals = rows.aggregate(
            total=Sum("quantity"),
            sellable=Sum("sellable"),
            reserved=Sum("reserved"),
        )
        sellable = totals["sellable"] or 0
        reserved = totals["reserved"] or 0
        return {
            "total": totals["total"] or 0,
            "sellable": sellable,
            "available": sellable - reserved,
        }

    def _resolve_inventory_warehouse(self, variant, business):
        """Pick the warehouse a business-scoped read should report against."""
        if business is None:
            return self.get_default_warehouse()
        warehouse = Warehouse.objects.filter(
            business=business, is_default=True
        ).first()
        if warehouse is not None:
            return warehouse
        row = (
            Inventory.objects.filter(variant=variant, business=business)
            .select_related("warehouse")
            .first()
        )
        if row is not None:
            return row.warehouse
        return self.get_default_warehouse()

    def get_stock_summary(self, variant, business=None):
        """Return total/sellable/available/strategy, optionally scoped to one business."""
        if self._detect_inventory_type(variant) == "normal":
            return {**self._normal_totals(variant, business=business), "strategy": "normal"}
        units = self._unit_queryset(variant, business=business)
        total = units.count()
        sellable = units.filter(state=InventoryUnitStateEnum.IN_STOCK.value).count()
        return {"total": total, "sellable": sellable, "available": sellable, "strategy": "serialized"}

    def get_summary(self, variant, business=None):
        inv_type = self._detect_inventory_type(variant)
        if inv_type == "normal":
            if business is not None:
                totals = self._normal_totals(variant, business=business)
                return {
                    "total_item_count": totals["total"],
                    "sellable_item_count": totals["sellable"],
                    "available_item_count": totals["available"],
                }
            inv = Inventory.objects.filter(variant=variant).first()
            if inv is None:
                return {"total_item_count": 0, "sellable_item_count": 0, "available_item_count": 0}
            return {
                "total_item_count": inv.quantity,
                "sellable_item_count": inv.sellable,
                "available_item_count": inv.available,
            }
        units = self._unit_queryset(variant, business=business)
        total = units.count()
        sellable = units.filter(state=InventoryUnitStateEnum.IN_STOCK.value).count()
        return {
            "total_item_count": total,
            "sellable_item_count": sellable,
            "available_item_count": sellable,
        }

    def get_variant_details(self, variant, business=None):
        from django.db.models import Sum
        from domains.inventory.models import InventorySupply

        inv_type = self._detect_inventory_type(variant)
        summary = self.get_summary(variant, business=business)
        primary_category = variant.product.categories.order_by("id").first()
        supply_rows = InventorySupply.objects.filter(variant=variant)
        if business is not None:
            supply_rows = supply_rows.filter(business=business)
        total_supply_quantity = (
            supply_rows.aggregate(total=Sum("quantity"))["total"] or 0
        )
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
        if inv_type == "normal":
            warehouse = self._resolve_inventory_warehouse(variant, business)
            inv_rows = Inventory.objects.filter(
                variant=variant, warehouse=warehouse
            )
            if business is not None:
                inv_rows = inv_rows.filter(business=business)
            inv = inv_rows.first()
            return {
                "variant_id": variant.id,
                **context,
                "strategy": {"id": 1, "code": "normal", "name": "Normal"},
                **summary,
                "total_supply_quantity": total_supply_quantity,
                "inventory": {
                    "warehouse": self.serialize_warehouse(warehouse),
                    "quantity": inv.quantity if inv else 0,
                    "sellable": inv.sellable if inv else 0,
                    "reserved": inv.reserved if inv else 0,
                    "available": inv.available if inv else 0,
                    "min_stock": inv.min_stock if inv else 0,
                },
                "serial_items": None,
            }
        serial_attr_def = InventoryAttributeDefinition.objects.filter(code="serial_number").first()
        units = self._unit_queryset(variant, business=business).select_related(
            "inventory__warehouse"
        ).order_by("id")
        if serial_attr_def:
            unit_ids = list(units.values_list("id", flat=True))
            attr_map = {
                a.inventory_unit_id: a.value
                for a in InventoryUnitAttribute.objects.filter(
                    inventory_unit_id__in=unit_ids,
                    attribute_definition=serial_attr_def,
                )
            }
        else:
            attr_map = {}
        warehouse_cache = {}
        return {
            "variant_id": variant.id,
            **context,
            "strategy": {"id": 2, "code": "serialized", "name": "Serialized"},
            **summary,
            "total_supply_quantity": total_supply_quantity,
            "inventory": None,
            "serial_items": [
                {
                    "id": unit.id,
                    "serial_number": attr_map.get(unit.id, ""),
                    "on_sale": unit.state == InventoryUnitStateEnum.IN_STOCK.value,
                    "reserved": unit.state == InventoryUnitStateEnum.RESERVED.value,
                    "status": {"code": unit.state, "name": unit.get_state_display()},
                    "warehouse": self._get_warehouse_for_unit(unit, warehouse_cache),
                    "editable": unit.state == InventoryUnitStateEnum.IN_STOCK.value,
                }
                for unit in units
            ],
        }

    @transaction.atomic
    def adjust_variant_stock(self, variant, *, inventory=None, serial_items=None):
        variant = type(variant).objects.select_for_update().select_related(
            "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).get(pk=variant.pk)
        inv_type = self._detect_inventory_type(variant)
        if inv_type == "serialized":
            self._apply_serialized_snapshot(variant, serial_items)
        else:
            warehouse = self.get_default_warehouse(lock=True)
            self._apply_normal(variant, warehouse, inventory)
        return type(variant).objects.select_related(
            "product"
        ).prefetch_related(
            "product__categories", "selections__attribute", "selections__option"
        ).get(pk=variant.pk)

    @staticmethod
    def _get_warehouse_for_unit(unit, cache):
        wh = unit.inventory.warehouse
        if wh.id not in cache:
            cache[wh.id] = InventoryService.serialize_warehouse(wh)
        return cache[wh.id]

    @staticmethod
    def serialize_warehouse(warehouse):
        return {
            "id": warehouse.id,
            "code": warehouse.code,
            "name": warehouse.name,
            "status": warehouse.status.name,
        }

    def validate_variant_deletion(self, variant):
        has_stock = Inventory.objects.filter(variant=variant, quantity__gt=0).exists()
        has_units = InventoryUnit.objects.filter(inventory__variant=variant).exists()
        if has_stock or has_units:
            raise self.ValidationError({
                "inventory": [_('A variant with stock cannot be deleted.')]
            })
        Inventory.objects.filter(variant=variant).delete()

    @transaction.atomic
    def receive_normal_stock(self, *, variant, warehouse, quantity, business=None):
        from domains.business.models import BusinessProfile

        if business is None:
            business = BusinessProfile.objects.get(id=1)
        inventory, created = Inventory.objects.select_for_update().get_or_create(
            business=business,
            warehouse=warehouse,
            variant=variant,
            defaults={"quantity": quantity, "sellable": 0, "reserved": 0},
        )
        if not created:
            inventory.quantity += quantity
            inventory.save(update_fields=["quantity"])

    @transaction.atomic
    def receive_serialized_stock(self, *, variant, warehouse, serial_numbers, supply, business=None):
        serial_attr_def = InventoryAttributeDefinition.objects.filter(code="serial_number").first()
        if serial_attr_def is None:
            raise self.ValidationError({
                "serial_items": [_('Inventory setup is missing the serial_number attribute definition.')]
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
        from domains.business.models import BusinessProfile

        if business is None:
            business = BusinessProfile.objects.get(id=1)
        inventory, _ = Inventory.objects.get_or_create(
            business=business,
            warehouse=warehouse,
            variant=variant,
            defaults={"quantity": 0, "sellable": 0, "reserved": 0},
        )
        try:
            with transaction.atomic():
                units = []
                attrs = []
                for value in normalized:
                    unit = InventoryUnit(
                        inventory=inventory,
                        state=InventoryUnitStateEnum.IN_STOCK.value,
                        supply=supply,
                    )
                    units.append(unit)
                created_units = InventoryUnit.objects.bulk_create(units)
                for unit, value in zip(created_units, normalized):
                    attrs.append(InventoryUnitAttribute(
                        inventory_unit=unit,
                        attribute_definition=serial_attr_def,
                        value=value,
                    ))
                InventoryUnitAttribute.objects.bulk_create(attrs)
        except IntegrityError as exc:
            raise self.ValidationError({
                "serial_items": [_('Serial numbers must be globally unique, ignoring case.')]
            }) from exc
        self._sync_inventory_summary(inventory)

    def _validate_transition(self, current_state, target_state):
        allowed = _VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise self.ValidationError({
                "state": [
                    _('Cannot transition from "%(current)s" to "%(target)s".')
                    % {"current": current_state, "target": target_state}
                ]
            })

    def _get_inventory(self, inventory_id, *, lock=False):
        qs = Inventory.objects.select_related("variant", "warehouse")
        if lock:
            qs = qs.select_for_update()
        return qs.filter(pk=inventory_id).first()

    def _get_unit(self, unit_id, *, lock=False):
        qs = InventoryUnit.objects.select_related("inventory")
        if lock:
            qs = qs.select_for_update()
        return qs.filter(pk=unit_id).first()

    def _sync_inventory_summary(self, inventory):
        units = InventoryUnit.objects.filter(inventory=inventory)
        inventory.quantity = units.count()
        inventory.sellable = units.filter(
            state=InventoryUnitStateEnum.IN_STOCK.value
        ).count()
        inventory.reserved = units.filter(
            state=InventoryUnitStateEnum.RESERVED.value
        ).count()
        inventory.save(update_fields=["quantity", "sellable", "reserved"])

    def _ensure_business(self):
        from domains.business.models import BusinessProfile
        return BusinessProfile.objects.get(id=1)

    @transaction.atomic
    def receive_stock(self, inventory_id, *, quantity=None, unit_count=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        is_serialized = InventoryUnit.objects.filter(inventory=inventory).exists()
        if is_serialized or unit_count is not None:
            if unit_count is None:
                raise self.ValidationError({
                    "unit_count": [_('Unit count is required for serialized inventory.')]
                })
            if unit_count <= 0:
                raise self.ValidationError({
                    "unit_count": [_('Unit count must be greater than zero.')]
                })
            units = [
                InventoryUnit(
                    inventory=inventory,
                    state=InventoryUnitStateEnum.IN_STOCK.value,
                )
                for _ in range(unit_count)
            ]
            InventoryUnit.objects.bulk_create(units)
            self._sync_inventory_summary(inventory)
        else:
            if quantity is None or quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Quantity must be greater than zero.')]
                })
            inventory.quantity += quantity
            inventory.save(update_fields=["quantity"])
        return inventory

    @transaction.atomic
    def increase_stock(self, inventory_id, quantity):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        if InventoryUnit.objects.filter(inventory=inventory).exists():
            raise self.ValidationError({
                "inventory": [_('Use receive_stock for serialized inventory.')]
            })
        if quantity <= 0:
            raise self.ValidationError({
                "quantity": [_('Quantity must be greater than zero.')]
            })
        inventory.quantity += quantity
        inventory.sellable += quantity
        inventory.save(update_fields=["quantity", "sellable"])
        return inventory

    @transaction.atomic
    def decrease_stock(self, inventory_id, quantity):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        if InventoryUnit.objects.filter(inventory=inventory).exists():
            raise self.ValidationError({
                "inventory": [_('Use unit-level operations for serialized inventory.')]
            })
        if quantity <= 0:
            raise self.ValidationError({
                "quantity": [_('Quantity must be greater than zero.')]
            })
        if quantity > inventory.sellable:
            raise self.ValidationError({
                "quantity": [
                    _('Cannot decrease more than sellable. Available: %(available)s.')
                    % {"available": inventory.sellable}
                ]
            })
        inventory.sellable -= quantity
        inventory.quantity -= quantity
        inventory.save(update_fields=["quantity", "sellable"])
        return inventory

    @transaction.atomic
    def reserve_stock(self, inventory_id, *, quantity=None, unit_ids=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        has_units = InventoryUnit.objects.filter(inventory=inventory).exists()
        if has_units or unit_ids is not None:
            if not unit_ids:
                raise self.ValidationError({
                    "unit_ids": [_('Unit IDs are required for serialized inventory.')]
                })
            units = list(
                InventoryUnit.objects.select_for_update().filter(
                    id__in=unit_ids, inventory=inventory
                )
            )
            if len(units) != len(unit_ids):
                raise self.ValidationError({
                    "unit_ids": [_('One or more unit IDs are invalid.')]
                })
            for unit in units:
                if unit.state != InventoryUnitStateEnum.IN_STOCK.value:
                    raise self.ValidationError({
                        "unit_ids": [
                            _('Unit %(id)s is in state "%(state)s" and cannot be reserved.')
                            % {"id": unit.id, "state": unit.state}
                        ]
                    })
            for unit in units:
                unit.state = InventoryUnitStateEnum.RESERVED.value
                unit.save(update_fields=["state"])
            self._sync_inventory_summary(inventory)
        else:
            if quantity is None or quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Quantity must be greater than zero.')]
                })
            if quantity > inventory.available:
                raise self.ValidationError({
                    "quantity": [
                        _('Cannot reserve more than available. Available: %(available)s.')
                        % {"available": inventory.available}
                    ]
                })
            inventory.reserved += quantity
            inventory.save(update_fields=["reserved"])
        return inventory

    @transaction.atomic
    def release_reservation(self, inventory_id, *, quantity=None, unit_ids=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        has_units = InventoryUnit.objects.filter(inventory=inventory).exists()
        if has_units or unit_ids is not None:
            if not unit_ids:
                raise self.ValidationError({
                    "unit_ids": [_('Unit IDs are required for serialized inventory.')]
                })
            units = list(
                InventoryUnit.objects.select_for_update().filter(
                    id__in=unit_ids, inventory=inventory
                )
            )
            if len(units) != len(unit_ids):
                raise self.ValidationError({
                    "unit_ids": [_('One or more unit IDs are invalid.')]
                })
            for unit in units:
                if unit.state != InventoryUnitStateEnum.RESERVED.value:
                    raise self.ValidationError({
                        "unit_ids": [
                            _('Unit %(id)s is in state "%(state)s" and is not reserved.')
                            % {"id": unit.id, "state": unit.state}
                        ]
                    })
            for unit in units:
                unit.state = InventoryUnitStateEnum.IN_STOCK.value
                unit.save(update_fields=["state"])
            self._sync_inventory_summary(inventory)
        else:
            if quantity is None or quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Quantity must be greater than zero.')]
                })
            if quantity > inventory.reserved:
                raise self.ValidationError({
                    "quantity": [
                        _('Cannot release more than reserved. Reserved: %(reserved)s.')
                        % {"reserved": inventory.reserved}
                    ]
                })
            inventory.reserved -= quantity
            inventory.save(update_fields=["reserved"])
        return inventory

    @transaction.atomic
    def sell_stock(self, inventory_id, *, quantity=None, unit_ids=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        has_units = InventoryUnit.objects.filter(inventory=inventory).exists()
        if has_units or unit_ids is not None:
            if not unit_ids:
                raise self.ValidationError({
                    "unit_ids": [_('Unit IDs are required for serialized inventory.')]
                })
            units = list(
                InventoryUnit.objects.select_for_update().filter(
                    id__in=unit_ids, inventory=inventory
                )
            )
            if len(units) != len(unit_ids):
                raise self.ValidationError({
                    "unit_ids": [_('One or more unit IDs are invalid.')]
                })
            for unit in units:
                if unit.state not in (
                    InventoryUnitStateEnum.IN_STOCK.value,
                    InventoryUnitStateEnum.RESERVED.value,
                ):
                    raise self.ValidationError({
                        "unit_ids": [
                            _('Unit %(id)s is in state "%(state)s" and cannot be sold.')
                            % {"id": unit.id, "state": unit.state}
                        ]
                    })
            for unit in units:
                unit.state = InventoryUnitStateEnum.SOLD.value
                unit.save(update_fields=["state"])
            self._sync_inventory_summary(inventory)
        else:
            if quantity is None or quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Quantity must be greater than zero.')]
                })
            if quantity > inventory.sellable:
                raise self.ValidationError({
                    "quantity": [
                        _('Cannot sell more than sellable. Sellable: %(sellable)s.')
                        % {"sellable": inventory.sellable}
                    ]
                })
            reserved_to_release = min(quantity, inventory.reserved)
            inventory.reserved -= reserved_to_release
            inventory.sellable -= quantity
            inventory.quantity -= quantity
            inventory.save(update_fields=["quantity", "sellable", "reserved"])
        return inventory

    @transaction.atomic
    def return_stock(self, inventory_id, *, quantity=None, unit_ids=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        has_units = InventoryUnit.objects.filter(inventory=inventory).exists()
        if has_units or unit_ids is not None:
            if not unit_ids:
                raise self.ValidationError({
                    "unit_ids": [_('Unit IDs are required for serialized inventory.')]
                })
            units = list(
                InventoryUnit.objects.select_for_update().filter(
                    id__in=unit_ids, inventory=inventory
                )
            )
            if len(units) != len(unit_ids):
                raise self.ValidationError({
                    "unit_ids": [_('One or more unit IDs are invalid.')]
                })
            for unit in units:
                if unit.state != InventoryUnitStateEnum.SOLD.value:
                    raise self.ValidationError({
                        "unit_ids": [
                            _('Unit %(id)s is in state "%(state)s" and cannot be returned.')
                            % {"id": unit.id, "state": unit.state}
                        ]
                    })
            for unit in units:
                unit.state = InventoryUnitStateEnum.RETURNED.value
                unit.save(update_fields=["state"])
            self._sync_inventory_summary(inventory)
        else:
            if quantity is None or quantity <= 0:
                raise self.ValidationError({
                    "quantity": [_('Quantity must be greater than zero.')]
                })
            inventory.quantity += quantity
            inventory.sellable += quantity
            inventory.save(update_fields=["quantity", "sellable"])
        return inventory

    @transaction.atomic
    def mark_damaged(self, inventory_id, unit_ids):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        if not InventoryUnit.objects.filter(inventory=inventory).exists():
            raise self.ValidationError({
                "inventory": [_('Mark damaged is only available for serialized inventory.')]
            })
        if not unit_ids:
            raise self.ValidationError({
                "unit_ids": [_('Unit IDs are required.')]
            })
        units = list(
            InventoryUnit.objects.select_for_update().filter(
                id__in=unit_ids, inventory=inventory
            )
        )
        if len(units) != len(unit_ids):
            raise self.ValidationError({
                "unit_ids": [_('One or more unit IDs are invalid.')]
            })
        for unit in units:
            self._validate_transition(unit.state, InventoryUnitStateEnum.DAMAGED.value)
        for unit in units:
            unit.state = InventoryUnitStateEnum.DAMAGED.value
            unit.save(update_fields=["state"])
        self._sync_inventory_summary(inventory)
        return inventory

    @transaction.atomic
    def mark_lost(self, inventory_id, unit_ids):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        if not InventoryUnit.objects.filter(inventory=inventory).exists():
            raise self.ValidationError({
                "inventory": [_('Mark lost is only available for serialized inventory.')]
            })
        if not unit_ids:
            raise self.ValidationError({
                "unit_ids": [_('Unit IDs are required.')]
            })
        units = list(
            InventoryUnit.objects.select_for_update().filter(
                id__in=unit_ids, inventory=inventory
            )
        )
        if len(units) != len(unit_ids):
            raise self.ValidationError({
                "unit_ids": [_('One or more unit IDs are invalid.')]
            })
        for unit in units:
            self._validate_transition(unit.state, InventoryUnitStateEnum.LOST.value)
        for unit in units:
            unit.state = InventoryUnitStateEnum.LOST.value
            unit.save(update_fields=["state"])
        self._sync_inventory_summary(inventory)
        return inventory

    @transaction.atomic
    def transfer_stock(self, source_inventory_id, destination_inventory_id, *, quantity=None, unit_ids=None, notes=""):
        source = self._get_inventory(source_inventory_id, lock=True)
        destination = self._get_inventory(destination_inventory_id, lock=True)
        if source is None:
            raise self.ValidationError({"source_inventory": [_('Source inventory not found.')]})
        if destination is None:
            raise self.ValidationError({"destination_inventory": [_('Destination inventory not found.')]})
        if source.id == destination.id:
            raise self.ValidationError({"destination_inventory": [_('Source and destination cannot be the same.')]})
        if source.variant_id != destination.variant_id:
            raise self.ValidationError({
                "destination_inventory": [_('Source and destination must hold the same variant.')]
            })

        has_source_units = InventoryUnit.objects.filter(inventory=source).exists()
        if has_source_units or unit_ids is not None:
            self._transfer_serialized(source, destination, unit_ids=unit_ids, notes=notes)
        else:
            self._transfer_normal(source, destination, quantity=quantity, notes=notes)
        return Inventory.objects.select_related("variant", "warehouse").filter(pk=source.id).first()

    @transaction.atomic
    def _transfer_normal(self, source, destination, *, quantity, notes):
        if quantity is None or quantity <= 0:
            raise self.ValidationError({
                "quantity": [_('Quantity must be greater than zero.')]
            })
        if quantity > source.sellable:
            raise self.ValidationError({
                "quantity": [
                    _('Cannot transfer more than sellable. Available: %(available)s.')
                    % {"available": source.sellable}
                ]
            })
        source.sellable -= quantity
        source.quantity -= quantity
        source.save(update_fields=["quantity", "sellable"])
        destination.quantity += quantity
        destination.save(update_fields=["quantity"])
        InventoryTransfer.objects.create(
            source_inventory=source,
            destination_inventory=destination,
            variant=source.variant,
            quantity=quantity,
            unit_count=0,
            notes=notes,
        )
        return source

    @transaction.atomic
    def _transfer_serialized(self, source, destination, *, unit_ids, notes):
        if not unit_ids:
            raise self.ValidationError({
                "unit_ids": [_('Unit IDs are required for serialized inventory.')]
            })
        units = list(
            InventoryUnit.objects.select_for_update().filter(
                id__in=unit_ids, inventory=source
            )
        )
        if len(units) != len(unit_ids):
            raise self.ValidationError({
                "unit_ids": [_('One or more unit IDs are invalid.')]
            })
        for unit in units:
            if unit.state not in (
                InventoryUnitStateEnum.IN_STOCK.value,
                InventoryUnitStateEnum.RESERVED.value,
            ):
                raise self.ValidationError({
                    "unit_ids": [
                        _('Unit %(id)s is in state "%(state)s" and cannot be transferred.')
                        % {"id": unit.id, "state": unit.state}
                    ]
                })
        for unit in units:
            unit.inventory_id = destination.id
            unit.save(update_fields=["inventory_id"])
        self._sync_inventory_summary(source)
        self._sync_inventory_summary(destination)
        InventoryTransfer.objects.create(
            source_inventory=source,
            destination_inventory=destination,
            variant=source.variant,
            quantity=len(units),
            unit_count=len(units),
            notes=notes,
        )
        return source
