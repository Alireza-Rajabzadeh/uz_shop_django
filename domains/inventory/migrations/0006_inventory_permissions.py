from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0005_serializedstockstatus_code_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="warehousestock",
            options={
                "permissions": [
                    ("view_inventory", "Can view inventory"),
                    ("adjust_stock", "Can adjust stock"),
                ],
            },
        ),
    ]
