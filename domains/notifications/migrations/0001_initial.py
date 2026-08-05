import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_notification_providers(apps, schema_editor):
    ProviderStatus = apps.get_model("notifications", "ProviderStatus")
    Provider = apps.get_model("notifications", "Provider")
    active, _ = ProviderStatus.objects.get_or_create(code="active", defaults={"name": "Active"})
    ProviderStatus.objects.get_or_create(code="inactive", defaults={"name": "Inactive"})
    Provider.objects.get_or_create(
        code="fake-sms",
        defaults={
            "name": "Fake SMS",
            "service_type": "sms",
            "status": active,
            "is_default": True,
        },
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="ProviderStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=50, unique=True)),
            ],
            options={"db_table": "notifications_provider_status", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Provider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("code", models.SlugField(max_length=50, unique=True)),
                ("service_type", models.CharField(choices=[("sms", "SMS"), ("email", "Email"), ("push", "Push notification")], max_length=20)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="providers", to="notifications.providerstatus")),
            ],
            options={"db_table": "notifications_provider", "ordering": ["service_type", "name"]},
        ),
        migrations.AddConstraint(
            model_name="provider",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("service_type",), name="notifications_one_default_per_type"),
        ),
        migrations.CreateModel(
            name="SentNotification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("service_type", models.CharField(choices=[("sms", "SMS"), ("email", "Email"), ("push", "Push notification")], max_length=20)),
                ("receiver", models.CharField(max_length=320)),
                ("message", models.TextField()),
                ("provider_code", models.CharField(max_length=50)),
                ("provider_name", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("delivered", "Delivered"), ("failed", "Failed")], default="pending", max_length=20)),
                ("external_id", models.CharField(blank=True, max_length=255)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sent_notifications", to=settings.AUTH_USER_MODEL)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sent_notifications", to="notifications.provider")),
            ],
            options={
                "db_table": "notifications_sent_notification",
                "ordering": ["-created_at"],
                "permissions": [("send_sms", "Can send SMS notifications")],
            },
        ),
        migrations.AddIndex(model_name="sentnotification", index=models.Index(fields=["status", "created_at"], name="notif_status_created_idx")),
        migrations.AddIndex(model_name="sentnotification", index=models.Index(fields=["provider", "created_at"], name="notif_provider_created_idx")),
        migrations.AddIndex(model_name="sentnotification", index=models.Index(fields=["receiver"], name="notifications_receiver_idx")),
        migrations.RunPython(seed_notification_providers, migrations.RunPython.noop),
    ]
