import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("files", "0002_file_statuses"),
        ("order", "0009_returnrequest_returnrequestitem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="returnrequest",
            name="refund_destination_type",
            field=models.CharField(
                choices=[("card", "Card"), ("account", "Account")],
                default="account",
                max_length=16,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="returnrequest",
            name="refund_destination_value",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name="ReturnRequestEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("file", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_request_evidence", to="files.file")),
                ("return_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence", to="order.returnrequest")),
            ],
            options={"db_table": "shop_return_request_evidence", "ordering": ["position", "id"]},
        ),
        migrations.AddConstraint(
            model_name="returnrequestevidence",
            constraint=models.UniqueConstraint(fields=("return_request", "position"), name="shop_return_unique_evidence_position"),
        ),
    ]
