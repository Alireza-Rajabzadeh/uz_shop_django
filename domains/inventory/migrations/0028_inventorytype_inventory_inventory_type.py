from django.db import migrations, models
import django.db.models.deletion


def seed_inventory_types(apps, schema_editor):
    InventoryType = apps.get_model("inventory", "InventoryType")
    InventoryType.objects.bulk_create([
        InventoryType(
            id=1,
            code="normal",
            name="Normal",
            fa_name="عادی",
            description="Quantity-based inventory without per-unit serial tracking.",
        ),
        InventoryType(
            id=2,
            code="serialized",
            name="Serialized",
            fa_name="سریالی",
            description="Inventory tracked as individually registered units.",
        ),
    ])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0027_alter_inventory_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryType",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("fa_name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True)),
            ],
            options={
                "db_table": "inventory_inventory_type",
                "ordering": ["id"],
            },
        ),
        migrations.RunPython(seed_inventory_types, migrations.RunPython.noop),
        migrations.AddField(
            model_name="inventory",
            name="inventory_type",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="inventories",
                to="inventory.inventorytype",
            ),
        ),
    ]