from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0025_remove_inventoryattribute"),
        ("order", "0015_remove_inventory_strategy"),
    ]

    operations = [
        migrations.DeleteModel(
            name="SerializedStock",
        ),
        migrations.DeleteModel(
            name="WarehouseStock",
        ),
        migrations.DeleteModel(
            name="SerializedStockStatus",
        ),
        migrations.DeleteModel(
            name="InventoryStrategy",
        ),
    ]
