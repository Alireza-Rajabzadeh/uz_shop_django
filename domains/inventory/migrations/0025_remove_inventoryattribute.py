from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0024_update_warehouse_default_constraint"),
    ]

    operations = [
        migrations.DeleteModel(
            name="InventoryAttribute",
        ),
    ]
