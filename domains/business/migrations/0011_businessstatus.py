from django.db import migrations, models
import django.db.models.deletion

from domains.business.data.business_statuses import BUSINESS_STATUS_SEED
from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum


def seed_business_statuses(apps, schema_editor):
    """Insert the three lifecycle statuses with fixed ids.

    Id 3 is `confirmation_await` because BusinessProfile.status defaults
    to it, so the default row must exist before the column does.
    """
    BusinessStatus = apps.get_model("business", "BusinessStatus")
    BusinessStatus.objects.bulk_create(
        [
            BusinessStatus(
                id=row["id"],
                code=row["code"],
                name=row["name"],
                title=row["title"],
            )
            for row in BUSINESS_STATUS_SEED
        ],
        ignore_conflicts=True,
    )


def backfill_active(apps, schema_editor):
    """Businesses that already exist are trading: they read as active.

    The column was just added with default 3, so every pre-existing row
    carries `confirmation_await`; moving them to `active` leaves only
    registrations made after this migration pending.
    """
    BusinessProfile = apps.get_model("business", "BusinessProfile")
    BusinessProfile.objects.filter(
        status_id=BusinessStatusEnum.CONFIRMATION_AWAIT.value
    ).update(status_id=BusinessStatusEnum.ACTIVE.value)


class Migration(migrations.Migration):

    dependencies = [
        ("business", "0010_businessprofile_package"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessStatus",
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
                ("code", models.CharField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "business_status",
            },
        ),
        migrations.RunPython(
            seed_business_statuses, reverse_code=migrations.RunPython.noop
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="status",
            field=models.ForeignKey(
                default=BusinessStatusEnum.CONFIRMATION_AWAIT.value,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="business_profiles",
                to="business.businessstatus",
            ),
        ),
        migrations.RunPython(backfill_active, migrations.RunPython.noop),
    ]
