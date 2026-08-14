import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0005_remove_orderstatus_next_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderAction",
            fields=[
                ("id", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("fa_name", models.CharField(max_length=100)),
                ("admin", models.BooleanField(default=False)),
                ("customer", models.BooleanField(default=False)),
                (
                    "set_status",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="result_actions",
                        to="order.orderstatus",
                    ),
                ),
            ],
            options={"db_table": "order_actions", "ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="OrderStatusAction",
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
                (
                    "order_action",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_assignments",
                        to="order.orderaction",
                    ),
                ),
                (
                    "order_status",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_actions",
                        to="order.orderstatus",
                    ),
                ),
            ],
            options={
                "db_table": "order_status_actions",
                "ordering": ["order_status_id", "order_action_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="orderstatusaction",
            constraint=models.UniqueConstraint(
                fields=("order_status", "order_action"),
                name="order_status_action_unique",
            ),
        ),
    ]
