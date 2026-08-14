import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("files", "0002_file_statuses"),
        ("order", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="PaymentMethod",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=50, unique=True)),
                        ("fa_name", models.CharField(max_length=50)),
                        ("available", models.BooleanField(default=True)),
                    ],
                    options={"db_table": "shop_order_payment_method", "ordering": ["id"]},
                ),
                migrations.CreateModel(
                    name="PaymentChannel",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=100, unique=True)),
                        ("fa_name", models.CharField(blank=True, default="", max_length=100)),
                        ("account_number", models.CharField(blank=True, max_length=50, null=True)),
                        ("card_number", models.CharField(blank=True, max_length=30, null=True)),
                        ("owner_name", models.CharField(blank=True, max_length=150, null=True)),
                        ("extra_data", models.JSONField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "shop_order_payment_channel", "ordering": ["id"]},
                ),
                migrations.CreateModel(
                    name="Payment",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("amount", models.DecimalField(decimal_places=2, max_digits=15)),
                        ("status", models.CharField(default="pending", max_length=16)),
                        ("ref_number", models.CharField(blank=True, max_length=128, null=True)),
                        ("resource_account_number", models.CharField(blank=True, max_length=64, null=True)),
                        ("extra_data", models.JSONField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="order.order")),
                        ("payment_channel", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="payments.paymentchannel")),
                        ("payment_method", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="payments.paymentmethod")),
                    ],
                    options={
                        "db_table": "shop_order_payment",
                        "indexes": [models.Index(fields=["order"], name="shop_order_payment_order_idx")],
                    },
                ),
                migrations.CreateModel(
                    name="PaymentChannelSupportedMethod",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("payment_channel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supported_methods", to="payments.paymentchannel")),
                        ("payment_method", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supported_channels", to="payments.paymentmethod")),
                    ],
                    options={
                        "db_table": "shop_order_payment_channel_support",
                        "constraints": [models.UniqueConstraint(fields=("payment_channel", "payment_method"), name="shop_payment_channel_support_unique")],
                    },
                ),
            ],
        ),
    ]
