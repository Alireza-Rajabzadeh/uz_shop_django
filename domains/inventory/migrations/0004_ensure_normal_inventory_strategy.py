from django.db import migrations


def ensure_normal_inventory_strategy(apps, schema_editor):
    InventoryStrategy = apps.get_model("inventory", "InventoryStrategy")
    InventoryStrategy.objects.update_or_create(
        code="normal",
        defaults={
            "name": "Normal",
            "description": "Stock tracked as an aggregate quantity for each variant.",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0003_serializedstockstatus_serializedstock_warehousestock"),
    ]

    operations = [
        migrations.RunPython(
            ensure_normal_inventory_strategy,
            migrations.RunPython.noop,
        ),
    ]
