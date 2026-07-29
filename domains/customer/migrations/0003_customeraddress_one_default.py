from django.db import migrations, models


def remove_duplicate_defaults(apps, schema_editor):
    CustomerAddress = apps.get_model("customer", "CustomerAddress")
    default_addresses = CustomerAddress.objects.filter(is_default=True).order_by(
        "customer_id", "-updated_at", "-id"
    )
    seen_customers = set()
    duplicate_ids = []
    for address in default_addresses.iterator():
        if address.customer_id in seen_customers:
            duplicate_ids.append(address.id)
        else:
            seen_customers.add(address.customer_id)
    CustomerAddress.objects.filter(id__in=duplicate_ids).update(is_default=False)


class Migration(migrations.Migration):
    dependencies = [
        ("customer", "0002_customer_abstractbaseuser"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_defaults, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="customeraddress",
            constraint=models.UniqueConstraint(
                fields=("customer",),
                condition=models.Q(is_default=True),
                name="customer_one_default_address",
            ),
        ),
    ]
