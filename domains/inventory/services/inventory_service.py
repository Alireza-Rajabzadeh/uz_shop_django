import uuid
from datetime import timedelta
from typing import NamedTuple

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.catalog.models import Category
from domains.inventory.enums.InventoryUnitStateEnum import (
    HISTORICAL_STATES,
    LIVE_STATES,
    InventoryUnitStateEnum,
)
from domains.inventory.models import (
    Inventory,
    InventoryType,
    InventoryTransfer,
    InventoryUnit,
    InventoryUnitAttribute,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services.inventory_attribute_service import (
    InventoryAttributeService,
)
from domains.marketplace.models import BusinessOffer

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


class ReservationEntry(NamedTuple):
    """What a checkout must persist for one held piece of stock.

    Field order matches the legacy shop reservation tuple, so callers can
    unpack it directly. ``inventory_type`` / ``inventory_id`` exist only to
    fill the shop table's historical generic columns; ``inventory`` and
    ``unit`` are the rows the inventory service actually acts on.
    """

    inventory_type: str
    inventory_id: int
    quantity: int
    inventory: Inventory
    unit: InventoryUnit | None


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
        inventory_type = self._get_inventory_type(variant)
        type_data = {
            "id": inventory_type.id,
            "code": inventory_type.code,
            "name": inventory_type.name,
            "fa_name": inventory_type.fa_name,
        }
        strategy = {
            "id": inventory_type.id,
            "code": inventory_type.code,
            "name": inventory_type.name,
        }
        return {
            "variant": variant.id,
            "sku": variant.sku,
            "product_id": variant.product_id,
            "product_name": variant.product.name,
            "category_id": primary_category.id if primary_category else None,
            "category_name": primary_category.name if primary_category else None,
            "inventory_type": type_data,
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
        # Inventory.quantity/sellable/reserved are the single source of truth
        # for a variant's stock. Serialized rows are re-derived from their units
        # by _sync_inventory_summary on every unit mutation, so the unit rows
        # must not be added on top of them: that counted serialized stock twice
        # (and counted `changed_type` residue as if it were still stock).
        inventory_sub = Inventory.objects.filter(variant_id=OuterRef("pk")).values("variant_id")
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
        ).annotate(
            total_item_count=F("inv_quantity"),
            sellable_item_count=F("inv_sellable"),
            available_item_count=F("inv_sellable") - F("inv_reserved"),
            reserved_item_count=F("inv_reserved"),
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

    def get_default_warehouse(self, *, business=None, lock=False):
        queryset = Warehouse.objects.select_related("status")
        if business is not None:
            queryset = queryset.filter(business=business)
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
        business=None,
    ):
        if not inventory_submitted:
            return
        requested_type = "serialized" if serial_items is not None else "normal"
        current_type = self._detect_inventory_type(variant, business=business)
        if current_type != requested_type:
            self._ensure_inventory_type_change_allowed(variant, business)
            if requested_type == "serialized":
                inventories = Inventory.objects.filter(variant=variant)
                if business is not None:
                    inventories = inventories.filter(business=business)
                if inventories.filter(quantity__gt=0).exists() and not serial_items:
                    raise self.ValidationError({
                        "serial_items": [_('Define serialized units before converting stocked inventory.')]
                    })
                self._apply_serialized_snapshot(variant, serial_items, business=business)
            else:
                self._convert_serialized_to_normal(variant, business=business)
            return
        if requested_type == "serialized":
            self._apply_serialized_snapshot(variant, serial_items, business=business)
        else:
            warehouse = self.get_default_warehouse(business=business, lock=True)
            self._apply_normal(variant, warehouse, inventory, business=business)

    def _apply_normal(self, variant, warehouse, inventory, business=None):
        if inventory is None:
            raise self.ValidationError({"inventory": [_('This field is required for normal inventory.')]})
        inventories = Inventory.objects.select_for_update().filter(
            variant=variant, warehouse=warehouse
        )
        if business is not None:
            inventories = inventories.filter(business=business)
        inv = inventories.first()
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
            business = business or BusinessProfile.objects.get(id=1)
            inv = Inventory.objects.create(
                business=business,
                warehouse=warehouse,
                variant=variant,
                inventory_type_id=1,
                quantity=quantity,
                sellable=sellable,
                reserved=reserved,
                min_stock=min_stock,
            )
        else:
            inv.inventory_type_id = 1
            inv.quantity = quantity
            inv.sellable = sellable
            inv.reserved = reserved
            inv.min_stock = min_stock
            inv.save(update_fields=["quantity", "sellable", "reserved", "min_stock"])

    def _apply_serialized_snapshot(self, variant, serial_items, business=None):
        if serial_items is None:
            raise self.ValidationError({
                "serial_items": [_('This field is required for serialized inventory.')]
            })
        inventories = Inventory.objects.filter(variant=variant)
        if business is not None:
            inventories = inventories.filter(business=business)
        inventory = inventories.first()
        if inventory is None:
            # Resolve the warehouse with the caller's business (which may be
            # unset), mirroring _apply_normal. Only the row itself needs the
            # singleton fallback, because Inventory.business is NOT NULL.
            warehouse = self.get_default_warehouse(business=business, lock=True)
            from domains.business.models import BusinessProfile
            inventory = Inventory.objects.create(
                business=business or BusinessProfile.objects.get(id=1),
                warehouse=warehouse,
                variant=variant,
                inventory_type_id=2,
                quantity=0,
                sellable=0,
                reserved=0,
            )
        # Attribute codes resolve against the caller's business when there is
        # one, otherwise against the inventory row's own business, so the
        # admin path (business=None) still sees business-owned definitions.
        owner = business or inventory.business
        serial_attr_def = InventoryAttributeService.resolve_definition(
            "serial_number", owner
        )
        if serial_attr_def is None:
            raise self.ValidationError({
                "serial_items": [_('Inventory setup is missing the serial_number attribute definition.')]
            })
        inventory.inventory_type_id = 2
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

        # Historical rows are out of scope: never deleted, never rewritten,
        # whether or not the client echoes them back. Only live units take part
        # in the diff.
        omitted = [
            unit
            for unit_id, unit in existing.items()
            if unit_id not in supplied_ids and unit.state not in HISTORICAL_STATES
        ]
        protected_omitted = [unit for unit in omitted if not self._is_editable(unit)]
        if protected_omitted:
            raise self.ValidationError({
                "serial_items": [_('Reserved serialized rows cannot be deleted.')]
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

        # Resolve and validate every row's attributes before touching any row,
        # so an unknown code or a type-invalid value cannot leave a partial
        # snapshot. Rows the diff skips (historical units) are never rewritten,
        # so their attributes are not validated either.
        prepared_attributes = []
        for item in serial_items:
            row_id = item.get("id")
            if row_id is not None and existing[row_id].state in HISTORICAL_STATES:
                prepared_attributes.append(None)
                continue
            try:
                prepared_attributes.append(
                    InventoryAttributeService.prepare_attributes(
                        item.get("attributes"), owner
                    )
                )
            except InventoryAttributeService.ValidationError as exc:
                # Same envelope, this service's own error type: translate it
                # into the error the inventory views already handle.
                raise self.ValidationError(exc.errors) from exc
        existing_attributes = {}
        for attribute in InventoryUnitAttribute.objects.filter(
            inventory_unit_id__in=existing_unit_ids
        ).exclude(attribute_definition=serial_attr_def):
            existing_attributes.setdefault(attribute.inventory_unit_id, {})[
                attribute.attribute_definition_id
            ] = attribute.value

        try:
            with transaction.atomic():
                for unit in omitted:
                    InventoryUnitAttribute.objects.filter(inventory_unit=unit).delete()
                    unit.delete()
                changed_existing = []
                for item, serial_number, attributes in zip(
                    serial_items, normalized_serials, prepared_attributes
                ):
                    row_id = item.get("id")
                    if row_id is None:
                        continue
                    unit = existing[row_id]
                    if unit.state in HISTORICAL_STATES:
                        continue
                    attr = existing_attrs.get(row_id)
                    old_serial = attr.value if attr else ""
                    on_sale = item["on_sale"]
                    desired_state = InventoryUnitStateEnum.IN_STOCK.value if on_sale else InventoryUnitStateEnum.RESERVED.value
                    serial_changed = old_serial != serial_number
                    state_changed = unit.state != desired_state
                    # An attribute edit is an edit: a reserved row refuses it
                    # like any other change, but it does not rewrite the serial
                    # number, so it never joins the placeholder pass below.
                    changed = (
                        serial_changed
                        or state_changed
                        or attributes != existing_attributes.get(row_id, {})
                    )
                    if changed and not self._is_editable(unit):
                        raise self.ValidationError({
                            "serial_items": [_('Reserved serialized rows cannot be edited.')]
                        })
                    if serial_changed or state_changed:
                        changed_existing.append((unit, serial_number, desired_state))

                for changed in changed_existing:
                    unit = changed[0]
                    InventoryUnitAttribute.objects.filter(
                        inventory_unit=unit, attribute_definition=serial_attr_def
                    ).update(value=f"__inventory_tmp_{unit.id}_{uuid.uuid4().hex}")

                for item, serial_number, attributes in zip(
                    serial_items, normalized_serials, prepared_attributes
                ):
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
                        InventoryAttributeService.apply_unit_attributes(
                            new_unit, attributes
                        )
                        continue
                    unit = existing[row_id]
                    if unit.state in HISTORICAL_STATES:
                        continue
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
                    # Historical rows never reach here, so `attributes` is
                    # always the validated map for this unit.
                    InventoryAttributeService.apply_unit_attributes(unit, attributes)
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

    INVENTORY_TYPE_CHANGE_REASON = _(
        'Deactivate the marketplace offer before changing inventory type.'
    )

    def inventory_type_change_gate(self, variant, business=None):
        """Non-raising flavour of the inventory type gate.

        Returns ``(allowed, reason)`` so API consumers can render the rule
        before the vendor attempts the change.
        """
        if business is not None and BusinessOffer.objects.filter(
            variant=variant,
            business=business,
            is_active=True,
        ).exists():
            return False, str(self.INVENTORY_TYPE_CHANGE_REASON)
        return True, None

    def _ensure_inventory_type_change_allowed(self, variant, business):
        allowed, reason = self.inventory_type_change_gate(variant, business)
        if not allowed:
            raise self.ValidationError({"inventory_type": [reason]})

    def _convert_serialized_to_normal(self, variant, *, business=None):
        from domains.inventory.models import InventorySupply

        inventories = Inventory.objects.select_for_update().filter(variant=variant)
        supplies = InventorySupply.objects.filter(
            variant=variant,
            received_at__isnull=False,
        )
        if business is not None:
            inventories = inventories.filter(business=business)
            supplies = supplies.filter(business=business)
        received_totals = {
            row["warehouse_id"]: row["total"]
            for row in supplies.values("warehouse_id").annotate(total=Sum("quantity"))
        }

        for inventory in inventories:
            units = list(
                InventoryUnit.objects.select_for_update().filter(inventory=inventory)
            )
            in_stock = sum(
                unit.state == InventoryUnitStateEnum.IN_STOCK.value for unit in units
            )
            reserved = sum(
                unit.state == InventoryUnitStateEnum.RESERVED.value for unit in units
            )
            if inventory.warehouse_id not in received_totals and (in_stock or reserved):
                # refresh_normal_inventory_from_supplies would fail with a
                # message written for routine refreshes; during a conversion the
                # vendor's first step is receiving supplies.
                raise self.ValidationError({
                    "inventory_type": [
                        _('Receive supplies before converting serialized inventory to normal.')
                    ]
                })
            for unit in units:
                if unit.state in LIVE_STATES:
                    unit.state = InventoryUnitStateEnum.CHANGED_TYPE.value
                    unit.save(update_fields=["state"])
            inventory.inventory_type_id = 1
            # `available` is sellable - reserved, so sellable has to hold every
            # live unit to keep availability identical across the conversion.
            inventory.sellable = in_stock + reserved
            inventory.reserved = reserved
            inventory.save(update_fields=["inventory_type", "sellable", "reserved"])

        # `quantity` is the only field derived from received supplies, so the
        # counts above have to be written first: the refresh guards compare
        # quantity against reserved and sellable.
        self.refresh_normal_inventory_from_supplies(
            variant=variant, business=business
        )

    def _get_inventory_type(self, variant, business=None):
        inventory_queryset = Inventory.objects
        unit_queryset = InventoryUnit.objects
        if business is not None:
            inventory_queryset = inventory_queryset.filter(business=business)
            unit_queryset = unit_queryset.filter(inventory__business=business)
        inventory = inventory_queryset.select_related("inventory_type").filter(
            variant=variant
        ).order_by("id").first()
        # Only live units report "serialized". Historical rows (sold, returned,
        # damaged, lost, frozen, changed_type) are a record of the past and
        # must not keep a converted variant stuck on the serialized strategy.
        if unit_queryset.filter(
            inventory__variant=variant,
            state__in=LIVE_STATES,
        ).exists():
            return InventoryType.objects.get(id=2)
        if inventory is None:
            return InventoryType.objects.get(id=1)
        return inventory.inventory_type

    def _detect_inventory_type(self, variant, business=None):
        return self._get_inventory_type(variant, business=business).code

    def get_inventory_types(self):
        """Options for the inventory type (normal / serialized) selector.

        Cost strategies are a separate pricing concern served by
        ``InventoryPricingService.get_strategies()``.
        """
        return [
            {
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "fa_name": item.fa_name,
            }
            for item in InventoryType.objects.all()
        ]

    def get_summary(self, variant, business=None, inv_type=None):
        # Callers that already resolved the type pass it in: detection is two
        # queries, and a list would otherwise pay for it twice per row.
        if inv_type is None:
            inv_type = self._detect_inventory_type(variant, business=business)
        if inv_type == "normal":
            inventories = Inventory.objects.filter(variant=variant)
            if business is not None:
                inventories = inventories.filter(business=business)
            inv = inventories.order_by("id").first()
            if inv is None:
                return {"total_item_count": 0, "sellable_item_count": 0, "available_item_count": 0}
            return {
                "total_item_count": inv.quantity,
                "sellable_item_count": inv.sellable,
                "available_item_count": inv.available,
            }
        units = InventoryUnit.objects.filter(inventory__variant=variant)
        if business is not None:
            units = units.filter(inventory__business=business)
        # changed_type rows are the residue of a type conversion: auditable but
        # never stock.
        total = units.exclude(
            state=InventoryUnitStateEnum.CHANGED_TYPE.value
        ).count()
        sellable = units.filter(state=InventoryUnitStateEnum.IN_STOCK.value).count()
        return {
            "total_item_count": total,
            "sellable_item_count": sellable,
            "available_item_count": sellable,
        }

    def get_stock_snapshot(self, variant, business=None):
        """Stock counts plus the strategy row, in one pass.

        Lists need both, and the strategy row is what ``get_summary`` spends
        its detection queries on anyway, so resolving it first and handing it
        back keeps a row at the same query cost as a bare summary. The
        strategy columns are keyed for API rows: callers merge the result into
        a serialized variant.
        """
        inventory_type = self._get_inventory_type(variant, business=business)
        return {
            "inventory_strategy": inventory_type.id,
            "inventory_strategy_code": inventory_type.code,
            "inventory_strategy_name": inventory_type.fa_name or inventory_type.name,
            **self.get_summary(variant, business=business, inv_type=inventory_type.code),
        }

    def get_variant_details(self, variant, business=None):
        from django.db.models import Sum
        from domains.inventory.models import InventorySupply

        inv_type = self._detect_inventory_type(variant, business=business)
        summary = self.get_summary(variant, business=business)
        inventory_type = self._get_inventory_type(variant, business=business)
        primary_category = variant.product.categories.order_by("id").first()
        total_supply_quantity = (
            InventorySupply.objects.filter(
                variant=variant
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
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
            "inventory_type": {
                "id": inventory_type.id,
                "code": inventory_type.code,
                "name": inventory_type.name,
                "fa_name": inventory_type.fa_name,
            },
        }
        if inv_type == "normal":
            inventories = Inventory.objects.select_related("warehouse__status").filter(
                variant=variant
            )
            if business is not None:
                inventories = inventories.filter(business=business)
            inv = inventories.order_by("-warehouse__is_default", "id").first()
            warehouse = inv.warehouse if inv else self.get_default_warehouse(business=business)
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
        serial_attr_def = InventoryAttributeService.resolve_definition(
            "serial_number", business
        )
        units = InventoryUnit.objects.filter(
            inventory__variant=variant
        ).exclude(
            state=InventoryUnitStateEnum.CHANGED_TYPE.value
        ).select_related("inventory__warehouse").order_by("id")
        if business is not None:
            units = units.filter(inventory__business=business)
        unit_ids = list(units.values_list("id", flat=True))
        if serial_attr_def:
            attr_map = {
                a.inventory_unit_id: a.value
                for a in InventoryUnitAttribute.objects.filter(
                    inventory_unit_id__in=unit_ids,
                    attribute_definition=serial_attr_def,
                )
            }
        else:
            attr_map = {}
        attributes_map = InventoryAttributeService.list_unit_attributes(unit_ids)
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
                    "attributes": attributes_map.get(unit.id, []),
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
        serial_attr_def = InventoryAttributeService.resolve_definition(
            "serial_number", business
        )
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
            defaults={
                "inventory_type_id": 2,
                "quantity": 0,
                "sellable": 0,
                "reserved": 0,
            },
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
        units = InventoryUnit.objects.filter(inventory=inventory).exclude(
            state=InventoryUnitStateEnum.CHANGED_TYPE.value
        )
        inventory.quantity = units.count()
        inventory.sellable = units.filter(
            state=InventoryUnitStateEnum.IN_STOCK.value
        ).count()
        inventory.reserved = units.filter(
            state=InventoryUnitStateEnum.RESERVED.value
        ).count()
        inventory.save(update_fields=[
            "inventory_type", "quantity", "sellable", "reserved"
        ])

    @transaction.atomic
    def refresh_serialized_inventory_from_units(self, *, variant, business=None):
        """Recompute serialized stock from its registered units.

        Serialized quantity is owned by the units rather than by received
        supplies, so a refresh recounts them instead of reading the supply
        ledger. Every unit mutation keeps this same summary in sync, so this
        is a re-derivation rather than a different source of truth.
        """
        inventories = Inventory.objects.select_for_update().filter(variant=variant)
        if business is not None:
            inventories = inventories.filter(business=business)
        synced = []
        for inventory in inventories:
            self._sync_inventory_summary(inventory)
            synced.append(inventory)
        return synced

    @transaction.atomic
    def refresh_variant_inventory(self, *, variant, business=None):
        """Recompute a variant's stock from whichever ledger owns it."""
        if self._detect_inventory_type(variant, business=business) == "serialized":
            return self.refresh_serialized_inventory_from_units(
                variant=variant, business=business
            )
        return self.refresh_normal_inventory_from_supplies(
            variant=variant, business=business
        )

    @transaction.atomic
    def refresh_normal_inventory_from_supplies(self, *, variant, business=None):
        if self._detect_inventory_type(variant, business=business) == "serialized":
            raise self.ValidationError({
                "inventory": [_('Serialized inventory is calculated from registered units.')]
            })

        from domains.inventory.models import InventorySupply

        supplies = InventorySupply.objects.filter(
            variant=variant,
            received_at__isnull=False,
        )
        inventories = Inventory.objects.select_for_update().filter(variant=variant)
        if business is not None:
            supplies = supplies.filter(business=business)
            inventories = inventories.filter(business=business)

        received_totals = {
            row["warehouse_id"]: row["total"]
            for row in supplies.values("warehouse_id").annotate(total=Sum("quantity"))
        }
        inventories = list(inventories)
        inventory_by_warehouse = {inventory.warehouse_id: inventory for inventory in inventories}

        for warehouse_id, quantity in received_totals.items():
            inventory = inventory_by_warehouse.get(warehouse_id)
            if inventory is None:
                warehouse = self.get_warehouse(warehouse_id)
                if warehouse is None:
                    continue
                inventory = Inventory.objects.create(
                    business=business,
                    warehouse=warehouse,
                    variant=variant,
                    inventory_type_id=1,
                )
                inventory_by_warehouse[warehouse_id] = inventory
            if inventory.reserved > quantity or inventory.sellable > quantity:
                raise self.ValidationError({
                    "inventory": [
                        _('Received supply quantity cannot be lower than reserved or sellable stock.')
                    ]
                })
            inventory.quantity = quantity
            inventory.save(update_fields=["quantity"])

        for inventory in inventories:
            if inventory.warehouse_id in received_totals:
                continue
            if inventory.reserved > 0 or inventory.sellable > 0:
                raise self.ValidationError({
                    "inventory": [
                        _('Inventory without received supplies still has reserved or sellable stock.')
                    ]
                })
            inventory.quantity = 0
            inventory.save(update_fields=["quantity"])

        return inventory_by_warehouse

    def _ensure_business(self):
        from domains.business.models import BusinessProfile
        return BusinessProfile.objects.get(id=1)

    @transaction.atomic
    def purge_changed_type_units(self, *, older_than_days=90, dry_run=False):
        """Drop `changed_type` units once they age past the retention window.

        A serialized -> normal conversion keeps those rows so the audit trail
        survives, but they are never sellable. Purging is deliberately manual —
        no beat schedule — so the retention window stays an operator decision.
        Returns the number of units deleted (or that would be deleted).
        """
        cutoff = timezone.now() - timedelta(days=older_than_days)
        units = InventoryUnit.objects.filter(
            state=InventoryUnitStateEnum.CHANGED_TYPE.value,
            updated_at__lt=cutoff,
        )
        if dry_run:
            return units.count()
        deleted, _ = units.delete()
        return deleted

    @staticmethod
    def _is_serialized_inventory(inventory):
        """An inventory is serialized when it declares so or still holds live units.

        Units left behind by a type conversion (changed_type/frozen) are history
        and do not make the inventory serialized.
        """
        if inventory.inventory_type_id == 2:
            return True
        return InventoryUnit.objects.filter(
            inventory=inventory,
            state__in=LIVE_STATES,
        ).exists()

    @transaction.atomic
    def receive_stock(self, inventory_id, *, quantity=None, unit_count=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        is_serialized = self._is_serialized_inventory(inventory)
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
        if self._is_serialized_inventory(inventory):
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
        if self._is_serialized_inventory(inventory):
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

    # ─────────────── order-level holds (shop + marketplace) ───────────────
    # Both the shop checkout and the marketplace checkout reserve, release and
    # consume stock through the three methods below. The reservation rows each
    # flow persists are its audit trail; the algorithm that actually moves
    # inventory lives here and nowhere else.

    @transaction.atomic
    def reserve_variant_stock(self, variant, quantity, *, business=None):
        """Hold ``quantity`` sellable units of ``variant`` for an order line.

        Returns the entries the caller must persist as reservation rows: one
        aggregate entry for normal stock, one entry per selected unit for
        serialized stock. The caller owns the row shape, not the selection.
        """
        if quantity <= 0:
            raise self.ValidationError({
                "quantity": [_('Quantity must be greater than zero.')]
            })
        inventory = self._locked_inventory(variant, business=business)
        if inventory is None:
            raise self.ValidationError({
                "inventory": [_('No inventory is configured for this item.')]
            })
        if self._is_serialized_inventory(inventory):
            return self._reserve_units(inventory, variant, quantity)
        if quantity > inventory.available:
            raise self.ValidationError({
                "items": [
                    _('Item %(sku)s does not have enough stock.')
                    % {"sku": variant.sku}
                ]
            })
        inventory.reserved += quantity
        inventory.save(update_fields=["reserved"])
        return [ReservationEntry("inventory", inventory.id, quantity, inventory, None)]

    @transaction.atomic
    def release_reserved_stock(self, reservations):
        """Return held stock to the sellable pool.

        ``reservations`` may be rows from either flow's reservation table; they
        only need ``linked_inventory_id``, ``linked_unit_id`` and ``quantity``,
        which both shapes share.
        """
        synced = set()
        for reservation in reservations:
            if reservation.linked_inventory_id is None:
                continue
            if reservation.linked_unit_id is not None:
                InventoryUnit.objects.filter(
                    id=reservation.linked_unit_id,
                    state=InventoryUnitStateEnum.RESERVED.value,
                ).update(state=InventoryUnitStateEnum.IN_STOCK.value)
                synced.add(reservation.linked_inventory_id)
            else:
                Inventory.objects.filter(
                    id=reservation.linked_inventory_id,
                ).update(reserved=F("reserved") - reservation.quantity)
        self._resync_inventories(synced)

    @transaction.atomic
    def consume_reserved_stock(self, reservations):
        """Convert held stock into a sale.

        Deliberately does not touch supply cost layers: COGS attribution is
        ``InventorySupplyService``'s concern and stays with the order item.
        """
        synced = set()
        for reservation in reservations:
            if reservation.linked_inventory_id is None:
                continue
            if reservation.linked_unit_id is not None:
                InventoryUnit.objects.filter(
                    id=reservation.linked_unit_id,
                ).update(state=InventoryUnitStateEnum.SOLD.value)
                synced.add(reservation.linked_inventory_id)
            else:
                Inventory.objects.filter(
                    id=reservation.linked_inventory_id,
                ).update(
                    reserved=F("reserved") - reservation.quantity,
                    sellable=F("sellable") - reservation.quantity,
                    quantity=F("quantity") - reservation.quantity,
                )
        self._resync_inventories(synced)

    def _resync_inventories(self, inventory_ids):
        for inventory in Inventory.objects.filter(id__in=inventory_ids):
            self._sync_inventory_summary(inventory)

    @staticmethod
    def _locked_inventory(variant, *, business=None):
        # ``first()`` orders by primary key, so concurrent checkouts of the
        # same variant always lock the same row in the same order.
        queryset = Inventory.objects.select_for_update().filter(variant=variant)
        if business is not None:
            queryset = queryset.filter(business=business)
        return queryset.order_by("id").first()

    def _reserve_units(self, inventory, variant, quantity):
        units = list(
            InventoryUnit.objects.select_for_update()
            .filter(
                inventory=inventory,
                state=InventoryUnitStateEnum.IN_STOCK.value,
            )
            .order_by("id")[:quantity]
        )
        if len(units) < quantity:
            raise self.ValidationError({
                "items": [
                    _('Item %(sku)s does not have enough stock.')
                    % {"sku": variant.sku}
                ]
            })
        entries = []
        for unit in units:
            unit.state = InventoryUnitStateEnum.RESERVED.value
            unit.save(update_fields=["state"])
            entries.append(
                ReservationEntry("inventory_unit", unit.id, 1, inventory, unit)
            )
        self._sync_inventory_summary(inventory)
        return entries

    @transaction.atomic
    def reserve_stock(self, inventory_id, *, quantity=None, unit_ids=None):
        inventory = self._get_inventory(inventory_id, lock=True)
        if inventory is None:
            raise self.ValidationError({"inventory": [_('Inventory not found.')]})
        has_units = self._is_serialized_inventory(inventory)
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
        has_units = self._is_serialized_inventory(inventory)
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
        has_units = self._is_serialized_inventory(inventory)
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
        has_units = self._is_serialized_inventory(inventory)
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
        if not self._is_serialized_inventory(inventory):
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
        if not self._is_serialized_inventory(inventory):
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

        has_source_units = self._is_serialized_inventory(source)
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
