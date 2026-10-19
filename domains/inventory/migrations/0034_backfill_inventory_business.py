"""Backfill the business owner of warehouses and supplies.

Inventory became a business-level feature: ``Inventory.business`` was already
``NOT NULL``, but ``Warehouse.business`` and ``InventorySupply.business`` still
allowed ``NULL``. Every existing row predates multi-business support, so it
belongs to the original singleton business (``id=1``, seeded by
``inventory.0022``). This migration assigns those rows so the following
schema migration can make both columns ``NOT NULL``.

Forward:
  1. Ensure BusinessProfile id=1 exists (same guard as ``inventory.0022``).
  2. Warehouse.business  NULL -> business 1.
  3. InventorySupply.business NULL -> business 1.

Reverse is a no-op: the pre-existing NULLs are not recoverable, and re-nulling
would only re-break the invariant the next migration enforces.
"""

from django.db import migrations


def _ensure_business_profile(apps):
    """Create BusinessProfile id=1 if it does not exist."""
    BusinessProfile = apps.get_model("business", "BusinessProfile")
    business, _ = BusinessProfile.objects.get_or_create(
        id=1,
        defaults={
            "business_name": "Migrated Business",
            "display_name": "Migrated",
        },
    )
    return business


def forwards(apps, schema_editor):
    business = _ensure_business_profile(apps)
    Warehouse = apps.get_model("inventory", "Warehouse")
    InventorySupply = apps.get_model("inventory", "InventorySupply")

    warehouses = Warehouse.objects.filter(business__isnull=True).update(business=business)
    supplies = InventorySupply.objects.filter(business__isnull=True).update(business=business)
    print(
        f"  Backfilled business: {warehouses} warehouses, {supplies} supplies -> business #{business.id}"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0033_alter_inventory_options"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
