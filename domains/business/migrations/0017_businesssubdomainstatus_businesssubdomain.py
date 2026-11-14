import django.db.models.deletion
from django.db import migrations, models

from domains.business.data.business_subdomain_statuses import BUSINESS_SUBDOMAIN_STATUS_SEED
from domains.business.enums import BusinessSubdomainEnum
from domains.business.models.business_subdomain import RESERVED_SUBDOMAINS


def seed_subdomain_statuses(apps, schema_editor):
    """Seed the reference statuses (active, redirect, reserved) with fixed ids."""
    BusinessSubdomainStatus = apps.get_model("business", "BusinessSubdomainStatus")
    BusinessSubdomainStatus.objects.bulk_create(
        [
            BusinessSubdomainStatus(
                id=row["id"],
                code=row["code"],
                name=row["name"],
                title=row["title"],
            )
            for row in BUSINESS_SUBDOMAIN_STATUS_SEED
        ],
        ignore_conflicts=True,
    )


def backfill_initial_subdomains(apps, schema_editor):
    """Provision an initial active BusinessSubdomain for every pre-existing business."""
    from core.utils import to_slug

    BusinessProfile = apps.get_model("business", "BusinessProfile")
    BusinessSubdomain = apps.get_model("business", "BusinessSubdomain")

    active_status_id = BusinessSubdomainEnum.ACTIVE.value
    used_subdomains = set(
        BusinessSubdomain.objects.values_list("subdomain", flat=True)
    ) | set(RESERVED_SUBDOMAINS)

    for profile in BusinessProfile.objects.all().order_by("id"):
        if BusinessSubdomain.objects.filter(business_id=profile.id, status_id=active_status_id).exists():
            continue

        raw_name = profile.business_name or profile.display_name or f"shop-{profile.id}"
        base_slug = to_slug(raw_name)
        if not base_slug or len(base_slug) < 3:
            base_slug = f"shop-{profile.id}"
        if len(base_slug) > 25:
            base_slug = base_slug[:25].rstrip("-")

        candidate = base_slug
        idx = 1
        while candidate in used_subdomains:
            candidate = f"{base_slug[:24]}-{idx}"
            idx += 1

        used_subdomains.add(candidate)
        BusinessSubdomain.objects.create(
            business_id=profile.id,
            subdomain=candidate,
            status_id=active_status_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0016_businesscharge'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessSubdomainStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True)),
                ('name', models.CharField(max_length=64)),
                ('title', models.CharField(max_length=64)),
            ],
            options={
                'verbose_name': 'Business Subdomain Status',
                'verbose_name_plural': 'Business Subdomain Statuses',
                'db_table': 'business_subdomain_status',
            },
        ),
        migrations.RunPython(
            seed_subdomain_statuses,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.CreateModel(
            name='BusinessSubdomain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subdomain', models.CharField(db_index=True, max_length=30, unique=True)),
                ('business', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subdomains', to='business.businessprofile')),
                ('status', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subdomains', to='business.businesssubdomainstatus')),
            ],
            options={
                'db_table': 'business_subdomain',
                'indexes': [models.Index(fields=['business', 'status'], name='idx_biz_subdomain_status')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('status_id', 1)), fields=('business',), name='unique_active_subdomain_per_business')],
            },
        ),
        migrations.RunPython(
            backfill_initial_subdomains,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
