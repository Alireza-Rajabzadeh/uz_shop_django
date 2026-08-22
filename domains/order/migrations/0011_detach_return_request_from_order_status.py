from django.db import migrations


def detach_return_action(apps, schema_editor):
    OrderAction = apps.get_model("order", "OrderAction")
    OrderAction.objects.filter(code="request_return").update(set_status=None)


def restore_return_action(apps, schema_editor):
    OrderAction = apps.get_model("order", "OrderAction")
    OrderStatus = apps.get_model("order", "OrderStatus")
    status = OrderStatus.objects.filter(name="return_requested").first()
    if status is not None:
        OrderAction.objects.filter(code="request_return").update(set_status=status)


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0010_return_refund_destination_and_evidence"),
    ]

    operations = [
        migrations.RunPython(detach_return_action, restore_return_action),
    ]
