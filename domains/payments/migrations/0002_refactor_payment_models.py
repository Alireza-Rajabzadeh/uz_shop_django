from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def validate_legacy_payments(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    invalid_amounts = Payment.objects.filter(amount__lte=0).count()
    duplicate_successes = (
        Payment.objects.filter(status="success")
        .values("order_id")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
        .count()
    )
    if invalid_amounts or duplicate_successes:
        raise RuntimeError(
            "Payment migration blocked: resolve "
            f"{invalid_amounts} non-positive payment amount(s) and "
            f"{duplicate_successes} order(s) with multiple successful payments."
        )


def populate_codes_and_labels(apps, schema_editor):
    PaymentMethod = apps.get_model("payments", "PaymentMethod")
    for method in PaymentMethod.objects.all():
        method.name = method.code
        method.save(update_fields=["name"])

    PaymentChannel = apps.get_model("payments", "PaymentChannel")
    used = set()
    for channel in PaymentChannel.objects.order_by("id"):
        base = "".join(
            character if character.isalnum() else "_"
            for character in channel.name.strip().casefold()
        ).strip("_") or f"channel_{channel.id}"
        code = base[:90]
        candidate = code
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{code[:90 - len(str(suffix))]}_{suffix}"
        used.add(candidate)
        channel.code = candidate
        channel.save(update_fields=["code"])

    Payment = apps.get_model("payments", "Payment")
    Payment.objects.filter(status="success").update(status="successful")


def restore_legacy_payment_statuses(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    Payment.objects.filter(status="successful").update(status="success")


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_adopt_order_payment_tables")]

    operations = [
        migrations.RenameField(model_name="paymentmethod", old_name="name", new_name="code"),
        migrations.RenameField(model_name="paymentmethod", old_name="available", new_name="is_active"),
        migrations.AddField(
            model_name="paymentmethod",
            name="name",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="paymentmethod", name="fa_name", field=models.CharField(max_length=100)
        ),
        migrations.AddField(
            model_name="paymentchannel",
            name="code",
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="paymentchannel", name="is_active", field=models.BooleanField(default=True)
        ),
        migrations.AddField(
            model_name="paymentchannel",
            name="logo_file",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="payment_channel_logos", to="files.file",
            ),
        ),
        migrations.AlterField(
            model_name="paymentchannel", name="name", field=models.CharField(max_length=100)
        ),
        migrations.RunPython(validate_legacy_payments, migrations.RunPython.noop),
        migrations.RunPython(
            populate_codes_and_labels,
            restore_legacy_payment_statuses,
        ),
        migrations.AlterField(
            model_name="paymentmethod", name="name", field=models.CharField(max_length=100)
        ),
        migrations.AlterField(
            model_name="paymentchannel", name="code", field=models.CharField(max_length=100, unique=True)
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("successful", "Successful"), ("failed", "Failed")],
                default="pending", max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(condition=Q(amount__gt=0), name="shop_payment_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["pending", "successful", "failed"]),
                name="shop_payment_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("order",), condition=Q(status="successful"),
                name="shop_payment_one_successful_order",
            ),
        ),
    ]
