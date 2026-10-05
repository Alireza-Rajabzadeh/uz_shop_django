from django.db import migrations

STATUS_SEED = (
    ("pending", "در انتظار پرداخت"),
    ("successful", "پرداخت موفق"),
    ("failed", "پرداخت ناموفق"),
)


def seed_statuses_and_create_index(apps, schema_editor):
    """Allow exactly one successful payment per marketplace order.

    ``MarketplaceOrderPayment.status`` points at a seeded reference row, so
    the value that identifies success is not knowable when the model is
    defined. The statuses are ensured here first (same rows the
    ``business_payments`` domain seeds) and the partial index is built against
    the resolved id, mirroring ``business_payments.0003``.
    """
    BusinessPaymentStatus = apps.get_model(
        "business_payments", "BusinessPaymentStatus"
    )
    for name, title in STATUS_SEED:
        BusinessPaymentStatus.objects.get_or_create(
            name=name, defaults={"title": title, "is_active": True}
        )
    successful_id = BusinessPaymentStatus.objects.get(name="successful").id
    schema_editor.execute(
        f"""
        CREATE UNIQUE INDEX marketplace_payment_one_successful_per_order
        ON marketplace_order_payment (order_id)
        WHERE status_id = {successful_id}
        """
    )


def drop_successful_unique_index(apps, schema_editor):
    schema_editor.execute(
        "DROP INDEX IF EXISTS marketplace_payment_one_successful_per_order"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("business_payments", "0003_seed_statuses_and_add_unique_index"),
        ("marketplace", "0008_order_flow_models"),
    ]

    operations = [
        migrations.RunPython(
            seed_statuses_and_create_index, drop_successful_unique_index
        ),
    ]
