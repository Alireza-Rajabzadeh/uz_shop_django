from django.db import migrations, models
import django.db.models.deletion


def backfill_channel_business(apps, schema_editor):
    BusinessProfile = apps.get_model("business", "BusinessProfile")
    BusinessPaymentChannel = apps.get_model(
        "business_payments", "BusinessPaymentChannel"
    )
    business = BusinessProfile.objects.order_by("id").first()
    if business is None:
        return
    BusinessPaymentChannel.objects.filter(business__isnull=True).update(
        business=business
    )


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0008_businesscategory"),
        ("business_payments", "0006_businesspaymentmethod_description"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="businesspaymentchannel",
            name="bpc_code_unique",
        ),
        migrations.AddField(
            model_name="businesspaymentchannel",
            name="business",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="business_payment_channels",
                to="business.businessprofile",
            ),
        ),
        migrations.RunPython(
            backfill_channel_business,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="businesspaymentchannel",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="business_payment_channels",
                to="business.businessprofile",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspaymentchannel",
            constraint=models.UniqueConstraint(
                fields=("business", "code"),
                name="bpc_business_code_unique",
            ),
        ),
    ]
