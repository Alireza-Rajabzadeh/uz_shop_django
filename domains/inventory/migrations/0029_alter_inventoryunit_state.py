from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0028_inventorytype_inventory_inventory_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inventoryunit",
            name="state",
            field=models.CharField(
                choices=[
                    ("in_stock", "In stock"),
                    ("reserved", "Reserved"),
                    ("sold", "Sold"),
                    ("returned", "Returned"),
                    ("damaged", "Damaged"),
                    ("lost", "Lost"),
                    ("frozen", "Frozen"),
                ],
                default="in_stock",
                max_length=20,
            ),
        ),
    ]
