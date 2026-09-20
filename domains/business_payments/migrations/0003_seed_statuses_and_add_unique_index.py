from django.db import migrations


def seed_statuses_and_create_index(apps, schema_editor):
    BusinessPaymentStatus = apps.get_model("business_payments", "BusinessPaymentStatus")
    for name, title in (
        ("pending", "در انتظار پرداخت"),
        ("successful", "پرداخت موفق"),
        ("failed", "پرداخت ناموفق"),
    ):
        BusinessPaymentStatus.objects.get_or_create(
            name=name, defaults={"title": title, "is_active": True}
        )
    successful_id = BusinessPaymentStatus.objects.get(name="successful").id
    schema_editor.execute(
        f"""
        CREATE UNIQUE INDEX bp_payment_one_successful_per_order
        ON business_payment (business_id, order_id)
        WHERE status_id = {successful_id}
        """
    )


def drop_successful_unique_index(apps, schema_editor):
    schema_editor.execute(
        "DROP INDEX IF EXISTS bp_payment_one_successful_per_order"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("business_payments", "0002_businesspaymentstatus_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_statuses_and_create_index, drop_successful_unique_index
        ),
    ]
