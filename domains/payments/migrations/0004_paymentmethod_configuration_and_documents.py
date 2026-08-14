import django.db.models.deletion
from django.db import migrations, models


def seed_payment_review_actions(apps, schema_editor):
    OrderAction = apps.get_model("order", "OrderAction")
    OrderStatus = apps.get_model("order", "OrderStatus")
    statuses = {
        "payment_processing": (120, "در حال پردازش پرداخت"),
        "paid": (100, "پرداخت شده"),
        "payment_failed": (130, "پرداخت ناموفق"),
    }
    for status_name, (status_id, fa_name) in statuses.items():
        status = OrderStatus.objects.filter(name=status_name).first()
        if status is None:
            status, _ = OrderStatus.objects.get_or_create(
                id=status_id,
                defaults={"name": status_name, "fa_name": fa_name},
            )
        if status.name != status_name or status.fa_name != fa_name:
            status.name = status_name
            status.fa_name = fa_name
            status.save(update_fields=["name", "fa_name"])
    rows = (
        (11, "submit_payment", "Submit payment", "ثبت پرداخت", False, True, "payment_processing"),
        (12, "approve_payment", "Approve payment", "تأیید پرداخت", True, False, "paid"),
        (13, "reject_payment", "Reject payment", "رد پرداخت", True, False, "payment_failed"),
    )
    for action_id, code, name, fa_name, admin, customer, status_name in rows:
        status = OrderStatus.objects.get(name=status_name)
        OrderAction.objects.update_or_create(
            id=action_id,
            defaults={
                "code": code,
                "name": name,
                "fa_name": fa_name,
                "admin": admin,
                "customer": customer,
                "set_status": status,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("files", "0002_file_statuses"),
        ("order", "0007_order_history"),
        ("payments", "0003_paymentmethod_icon_path"),
    ]

    operations = [
        migrations.RemoveField(model_name="paymentmethod", name="icon_path"),
        migrations.AddField(
            model_name="paymentmethod",
            name="icon_file",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="payment_method_icons", to="files.file",
            ),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="point_to_channel_field",
            field=models.CharField(
                blank=True,
                choices=[
                    ("card_number", "Card number"),
                    ("account_number", "Account number"),
                    ("owner_name", "Owner name"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="requires_documents",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="PaymentDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("file", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_documents", to="files.file")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="payments.payment")),
            ],
            options={"db_table": "shop_payment_document", "ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="paymentdocument",
            constraint=models.UniqueConstraint(fields=("payment", "file"), name="shop_payment_document_unique"),
        ),
        migrations.RunPython(seed_payment_review_actions, migrations.RunPython.noop),
    ]
