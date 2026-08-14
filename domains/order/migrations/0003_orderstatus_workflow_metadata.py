from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0002_transfer_payments_and_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderstatus",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="orderstatus",
            name="next_status",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="orderstatus",
            name="available_actions",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
