from django.db import migrations


def remove_legacy_reservations(apps, schema_editor):
    OrderItemReservation = apps.get_model("order", "OrderItemReservation")
    OrderItemReservation.objects.filter(
        inventory_type__in=["warehouse_stock", "serialized_stock"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0025_remove_inventoryattribute"),
        ("order", "0014_orderitemreservation_linked_inventory_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_legacy_reservations, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="orderitem",
            name="inventory_strategy",
        ),
    ]
