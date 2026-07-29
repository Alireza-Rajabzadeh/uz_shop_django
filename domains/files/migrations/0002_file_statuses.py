from django.db import migrations


STATUSES = ("pending", "available", "failed", "deleted")


def create_file_statuses(apps, schema_editor):
    FileStatus = apps.get_model("files", "FileStatus")
    for name in STATUSES:
        FileStatus.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("files", "0001_initial")]

    operations = [migrations.RunPython(create_file_statuses, migrations.RunPython.noop)]
