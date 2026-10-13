"""Give every existing business the default ``free`` package.

`BusinessProfile.package` defaults to the ``free`` tier for new rows, so
existing rows have to be brought in line. The backfill runs before any code
that reads the column.

Two deliberate choices:

- The tier is looked up by the literal ``"free"``, not by importing
  ``DEFAULT_PACKAGE_CODE``. A migration is frozen history: it must keep
  behaving exactly as it did when it was written, even if the constant later
  moves or changes meaning.
- Absence is tolerated. An environment that has not seeded packages keeps
  ``NULL`` here, and readers treat NULL as the default tier, rather than
  this migration failing on a database that simply is not seeded yet.

Covers the row `inventory.0022_migrate_inventory_data` inserts as
``BusinessProfile id=1``.
"""

from django.db import migrations, models


def backfill_default_package(apps, schema_editor):
    Package = apps.get_model("packages", "Package")
    BusinessProfile = apps.get_model("business", "BusinessProfile")

    default = Package.objects.filter(code="free").first()
    if default is None:
        return

    BusinessProfile.objects.filter(package__isnull=True).update(package=default)


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0009_advance_profile_sequence'),
        ('packages', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='package',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='business_profiles', to='packages.package'),
        ),
        migrations.RunPython(backfill_default_package, migrations.RunPython.noop),
    ]
