import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0006_order_actions"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("before_values", models.JSONField(default=dict)),
                ("after_values", models.JSONField(default=dict)),
                ("description", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "action",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="history_entries",
                        to="order.orderaction",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="order.order",
                    ),
                ),
            ],
            options={
                "db_table": "order_history",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="orderhistory",
            index=models.Index(
                fields=["order", "-created_at"],
                name="ord_hist_order_created_idx",
            ),
        ),
    ]
