import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("business", "0001_initial"),
        ("files", "0002_file_statuses"),
        ("order", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessPaymentMethod",
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
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=100)),
                ("fa_name", models.CharField(max_length=100)),
                (
                    "point_to_channel_field",
                    models.CharField(
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
                ("requires_documents", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_payment_methods",
                        to="business.businessprofile",
                    ),
                ),
                (
                    "icon_file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="business_payment_method_icons",
                        to="files.file",
                    ),
                ),
            ],
            options={
                "db_table": "business_payment_method",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="BusinessPaymentChannel",
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
                ("code", models.CharField(max_length=100)),
                ("name", models.CharField(max_length=100)),
                ("fa_name", models.CharField(blank=True, default="", max_length=100)),
                (
                    "account_number",
                    models.CharField(blank=True, max_length=50, null=True),
                ),
                (
                    "card_number",
                    models.CharField(blank=True, max_length=30, null=True),
                ),
                (
                    "owner_name",
                    models.CharField(blank=True, max_length=150, null=True),
                ),
                ("extra_data", models.JSONField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_payment_channels",
                        to="business.businessprofile",
                    ),
                ),
                (
                    "logo_file",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="business_payment_channel_logos",
                        to="files.file",
                    ),
                ),
            ],
            options={
                "db_table": "business_payment_channel",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="BusinessPayment",
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=15)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("successful", "Successful"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "ref_number",
                    models.CharField(blank=True, max_length=128, null=True),
                ),
                (
                    "resource_account_number",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                ("extra_data", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_payments",
                        to="business.businessprofile",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="business_payments",
                        to="order.order",
                    ),
                ),
                (
                    "payment_channel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payments",
                        to="business_payments.businesspaymentchannel",
                    ),
                ),
                (
                    "payment_method",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="business_payments.businesspaymentmethod",
                    ),
                ),
            ],
            options={
                "db_table": "business_payment",
            },
        ),
        migrations.CreateModel(
            name="BusinessPaymentChannelSupportedMethod",
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
                    "payment_channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supported_methods",
                        to="business_payments.businesspaymentchannel",
                    ),
                ),
                (
                    "payment_method",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="supported_channels",
                        to="business_payments.businesspaymentmethod",
                    ),
                ),
            ],
            options={
                "db_table": "business_payment_channel_support",
            },
        ),
        migrations.CreateModel(
            name="BusinessPaymentDocument",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="business_payment_documents",
                        to="files.file",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="business_payments.businesspayment",
                    ),
                ),
            ],
            options={
                "db_table": "business_payment_document",
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="businesspayment",
            index=models.Index(
                fields=["business"], name="bp_business_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="businesspayment",
            index=models.Index(
                fields=["order"], name="bp_order_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspaymentmethod",
            constraint=models.UniqueConstraint(
                fields=("business", "code"),
                name="bpm_business_code_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspaymentchannel",
            constraint=models.UniqueConstraint(
                fields=("business", "code"),
                name="bpc_business_code_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspaymentchannelsupportedmethod",
            constraint=models.UniqueConstraint(
                fields=("payment_channel", "payment_method"),
                name="bpc_support_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspayment",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="bp_payment_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspayment",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=["pending", "successful", "failed"]),
                name="bp_payment_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspayment",
            constraint=models.UniqueConstraint(
                fields=("business", "order"),
                condition=models.Q(status="successful"),
                name="bp_payment_one_successful_per_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="businesspaymentdocument",
            constraint=models.UniqueConstraint(
                fields=("payment", "file"),
                name="bp_payment_document_unique",
            ),
        ),
    ]
