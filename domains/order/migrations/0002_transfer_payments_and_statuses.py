import django.db.models.deletion
from django.db import migrations, models


MODEL_RENAMES = {
    "orderpayment": "payment",
    "orderpaymentmethod": "paymentmethod",
    "orderpaymentchannel": "paymentchannel",
    "orderpaymentchannelsupportmethod": "paymentchannelsupportedmethod",
}


def seed_statuses_and_transfer_content_types(apps, schema_editor):
    OrderStatus = apps.get_model("order", "OrderStatus")
    statuses = {
        100: ("payment_waiting", "در انتظار پرداخت"),
        110: ("failed", "ناموفق"),
        120: ("cancelled", "لغو شده"),
        130: ("expired", "منقضی"),
        200: ("paid", "پرداخت شده"),
    }
    Order = apps.get_model("order", "Order")
    old_rows = {row.name: row for row in OrderStatus.objects.all()}
    # Free canonical names before creating their fixed-ID rows, then repoint orders.
    for name in ("payment_waiting", "failed", "cancelled", "expired", "paid"):
        row = old_rows.get(name)
        target_id = next(status_id for status_id, value in statuses.items() if value[0] == name)
        if row and row.id != target_id:
            row.name = f"legacy_{name}_{row.id}"
            row.save(update_fields=["name"])
    canonical = {}
    for status_id, (name, fa_name) in statuses.items():
        canonical[name], _ = OrderStatus.objects.update_or_create(
            id=status_id, defaults={"name": name, "fa_name": fa_name}
        )
    transfers = {
        "payment_waiting": "payment_waiting",
        "expired": "expired",
        "success": "paid",
        "failed": "cancelled",
        "paid": "paid",
        "cancelled": "cancelled",
    }
    for old_name, new_name in transfers.items():
        row = old_rows.get(old_name)
        if row and row.id != canonical[new_name].id:
            Order.objects.filter(status_id=row.id).update(status_id=canonical[new_name].id)
            row.delete()

    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    for old_model, new_model in MODEL_RENAMES.items():
        old = ContentType.objects.filter(app_label="order", model=old_model).first()
        if old is None:
            continue
        target = ContentType.objects.filter(app_label="payments", model=new_model).first()
        if target is not None:
            Permission.objects.filter(content_type=target).delete()
            target.delete()
        old.app_label = "payments"
        old.model = new_model
        old.save(update_fields=["app_label", "model"])
        for permission in Permission.objects.filter(content_type=old):
            action = permission.codename.split("_", 1)[0]
            permission.codename = f"{action}_{new_model}"
            permission.name = f"Can {action} {new_model}"
            permission.save(update_fields=["codename", "name"])


def restore_legacy_statuses_and_content_types(apps, schema_editor):
    OrderStatus = apps.get_model("order", "OrderStatus")
    Order = apps.get_model("order", "Order")
    legacy = {}
    for status_id, name, fa_name in (
        (2, "success", "موفق"),
        (3, "failed", "ناموفق"),
    ):
        existing = OrderStatus.objects.filter(name=name).exclude(id=status_id).first()
        if existing is not None:
            existing.name = f"rollback_{name}_{existing.id}"
            existing.save(update_fields=["name"])
        legacy[name], _ = OrderStatus.objects.update_or_create(
            id=status_id,
            defaults={"name": name, "fa_name": fa_name},
        )
    Order.objects.filter(status__name="paid").update(status=legacy["success"])
    Order.objects.filter(status__name="cancelled").update(status=legacy["failed"])

    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    for old_model, new_model in MODEL_RENAMES.items():
        content_type = ContentType.objects.filter(
            app_label="payments", model=new_model
        ).first()
        if content_type is None:
            continue
        content_type.app_label = "order"
        content_type.model = old_model
        content_type.save(update_fields=["app_label", "model"])
        for permission in Permission.objects.filter(content_type=content_type):
            action = permission.codename.split("_", 1)[0]
            permission.codename = f"{action}_{old_model}"
            permission.name = f"Can {action} {old_model}"
            permission.save(update_fields=["codename", "name"])


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0001_initial"),
        ("payments", "0002_refactor_payment_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="OrderPaymentChannelSupportMethod"),
                migrations.DeleteModel(name="OrderPayment"),
                migrations.DeleteModel(name="OrderPaymentChannel"),
                migrations.DeleteModel(name="OrderPaymentMethod"),
            ],
        ),
        migrations.AlterField(
            model_name="order",
            name="successful_payment",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="finalized_order", to="payments.payment",
            ),
        ),
        migrations.RunPython(
            seed_statuses_and_transfer_content_types,
            restore_legacy_statuses_and_content_types,
        ),
    ]
