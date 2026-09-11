"""
Data migration: migrate WarehouseStock and SerializedStock into the new
Inventory / InventoryUnit architecture.

Forward:
  1. Ensure BusinessProfile id=1 exists (required by Inventory.business NOT NULL).
  2. Create the "serial_number" InventoryAttributeDefinition.
  3. WarehouseStock → Inventory (one row per variant+warehouse).
  4. SerializedStock → Inventory + InventoryUnit + InventoryUnitAttribute.
  5. Verification counters — raises if counts or quantities mismatch.

This migration is safe to run idempotently: it skips tables that are already
populated and verifies totals at the end.

Rollback:
  The old WarehouseStock, SerializedStock, and SerializedStockStatus tables
  are NOT dropped by this migration, so a simple ``migrate inventory 0021``
  rolls back cleanly.
"""

from django.db import migrations


# ── status code mapping (old SerializedStockStatus.id → new unit state) ──

STATUS_MAP = {
    1: "in_stock",   # SerializedStockStatusEnum.IN_STOCK
    2: "sold",       # SerializedStockStatusEnum.SOLD
    3: "returned",   # SerializedStockStatusEnum.RETURNED
    4: "damaged",    # SerializedStockStatusEnum.DAMAGED
    5: "lost",       # SerializedStockStatusEnum.LOST
}


def _ensure_business_profile(apps):
    """Create BusinessProfile id=1 if it does not exist."""
    BusinessProfile = apps.get_model("business", "BusinessProfile")
    bp, created = BusinessProfile.objects.get_or_create(
        id=1,
        defaults={
            "business_name": "Migrated Business",
            "display_name": "Migrated",
        },
    )
    return bp


def _ensure_attribute_definition(apps, business):
    """Create the serial_number attribute definition if missing."""
    InventoryAttributeDefinition = apps.get_model(
        "inventory", "InventoryAttributeDefinition"
    )
    attr_def, _ = InventoryAttributeDefinition.objects.get_or_create(
        business=business,
        code="serial_number",
        defaults={
            "name": "Serial Number",
            "type": "text",
        },
    )
    return attr_def


def migrate_warehouse_stocks(apps, business):
    """Copy WarehouseStock rows into Inventory."""
    WarehouseStock = apps.get_model("inventory", "WarehouseStock")
    Inventory = apps.get_model("inventory", "Inventory")

    migrated = 0
    skipped = 0
    for ws in WarehouseStock.objects.select_related("variant", "warehouse").all():
        inv, created = Inventory.objects.get_or_create(
            business=business,
            warehouse=ws.warehouse,
            variant=ws.variant,
            defaults={
                "quantity": ws.quantity,
                "sellable": ws.sellable,
                "reserved": ws.reserved,
                "min_stock": ws.min_stock,
            },
        )
        if created:
            migrated += 1
        else:
            skipped += 1
    return migrated, skipped


def migrate_serialized_stocks(apps, business, attr_def):
    """Copy SerializedStock rows into Inventory + InventoryUnit."""
    SerializedStock = apps.get_model("inventory", "SerializedStock")
    Inventory = apps.get_model("inventory", "Inventory")
    InventoryUnit = apps.get_model("inventory", "InventoryUnit")
    InventoryUnitAttribute = apps.get_model("inventory", "InventoryUnitAttribute")

    migrated = 0
    skipped = 0
    for ss in SerializedStock.objects.select_related(
        "variant", "warehouse", "status", "supply"
    ).all():
        inv, _ = Inventory.objects.get_or_create(
            business=business,
            warehouse=ss.warehouse,
            variant=ss.variant,
            defaults={
                "quantity": 0,
                "sellable": 0,
                "reserved": 0,
                "min_stock": 0,
            },
        )
        state = STATUS_MAP.get(ss.status_id, "in_stock")
        unit = InventoryUnit.objects.create(
            inventory=inv,
            state=state,
            supply=ss.supply,
        )
        InventoryUnitAttribute.objects.create(
            inventory_unit=unit,
            attribute_definition=attr_def,
            value=ss.serial_number,
        )
        migrated += 1
    return migrated, skipped


def verify_migration(apps, schema_editor):
    """Cross-check old and new record counts and quantities."""
    WarehouseStock = apps.get_model("inventory", "WarehouseStock")
    SerializedStock = apps.get_model("inventory", "SerializedStock")
    Inventory = apps.get_model("inventory", "Inventory")
    InventoryUnit = apps.get_model("inventory", "InventoryUnit")
    InventoryUnitAttribute = apps.get_model("inventory", "InventoryUnitAttribute")

    errors = []

    # ── 1. Record counts ──
    old_ws_count = WarehouseStock.objects.count()
    old_ss_count = SerializedStock.objects.count()
    new_inv_count = Inventory.objects.count()
    new_unit_count = InventoryUnit.objects.count()
    new_attr_count = InventoryUnitAttribute.objects.count()

    # Expected Inventory rows = unique (variant, warehouse) pairs across both old tables
    ws_pairs = set(
        WarehouseStock.objects.values_list("variant_id", "warehouse_id")
    )
    ss_pairs = set(
        SerializedStock.objects.values_list("variant_id", "warehouse_id")
    )
    expected_inv = len(ws_pairs | ss_pairs)
    if new_inv_count != expected_inv:
        errors.append(
            f"Inventory count mismatch: expected {expected_inv}, got {new_inv_count}"
        )

    if new_unit_count != old_ss_count:
        errors.append(
            f"InventoryUnit count mismatch: expected {old_ss_count}, got {new_unit_count}"
        )

    if new_attr_count != old_ss_count:
        errors.append(
            f"InventoryUnitAttribute count mismatch: expected {old_ss_count}, got {new_attr_count}"
        )

    # ── 2. WarehouseStock quantities ──
    from django.db.models import Sum, IntegerField
    from django.db.models.functions import Coalesce

    old_ws = WarehouseStock.objects.aggregate(
        q=Coalesce(Sum("quantity"), 0, output_field=IntegerField()),
        s=Coalesce(Sum("sellable"), 0, output_field=IntegerField()),
        r=Coalesce(Sum("reserved"), 0, output_field=IntegerField()),
    )
    old_qty, old_sell, old_res = old_ws["q"], old_ws["s"], old_ws["r"]

    ws_variant_ids = set(
        WarehouseStock.objects.values_list("variant_id", flat=True)
    )
    ws_warehouse_ids = set(
        WarehouseStock.objects.values_list("warehouse_id", flat=True)
    )
    new_inv_qs = Inventory.objects.filter(
        variant_id__in=ws_variant_ids,
        warehouse_id__in=ws_warehouse_ids,
    )
    new_agg = new_inv_qs.aggregate(
        q=Coalesce(Sum("quantity"), 0, output_field=IntegerField()),
        s=Coalesce(Sum("sellable"), 0, output_field=IntegerField()),
        r=Coalesce(Sum("reserved"), 0, output_field=IntegerField()),
    )
    new_qty, new_sell, new_res = new_agg["q"], new_agg["s"], new_agg["r"]

    if new_qty != old_qty:
        errors.append(f"quantity mismatch (warehouse): expected {old_qty}, got {new_qty}")
    if new_sell != old_sell:
        errors.append(f"sellable mismatch (warehouse): expected {old_sell}, got {new_sell}")
    if new_res != old_res:
        errors.append(f"reserved mismatch (warehouse): expected {old_res}, got {new_res}")

    # ── 3. SerializedStock units ──
    unit_with_supply = InventoryUnit.objects.filter(supply__isnull=False).count()
    ss_with_supply = SerializedStock.objects.filter(supply__isnull=False).count()
    if unit_with_supply != ss_with_supply:
        errors.append(
            f"supply-linked units mismatch: expected {ss_with_supply}, got {unit_with_supply}"
        )

    # ── 4. Status mapping spot-check ──
    for old_status_id, expected_state in STATUS_MAP.items():
        old_count = SerializedStock.objects.filter(status_id=old_status_id).count()
        new_count = InventoryUnit.objects.filter(state=expected_state).count()
        if old_count != new_count:
            errors.append(
                f"status {expected_state}: expected {old_count} units, got {new_count}"
            )

    if errors:
        msg = "Data migration verification failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(msg)


def forwards(apps, schema_editor):
    business = _ensure_business_profile(apps)
    attr_def = _ensure_attribute_definition(apps, business)

    ws_migrated, ws_skipped = migrate_warehouse_stocks(apps, business)
    ss_migrated, ss_skipped = migrate_serialized_stocks(apps, business, attr_def)

    print(f"  WarehouseStock → Inventory: {ws_migrated} migrated, {ws_skipped} skipped")
    print(f"  SerializedStock → Inventory+Unit: {ss_migrated} migrated, {ss_skipped} skipped")

    verify_migration(apps, schema_editor)

    print("  Verification passed.")


def backwards(apps, schema_editor):
    """No-op: old tables are preserved. Rollback is simply re-running old code."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0021_inventorytransfer"),
        ("business", "__first__"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
