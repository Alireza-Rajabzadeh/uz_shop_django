from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0003_orderstatus_workflow_metadata"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="orderstatus",
            name="available_actions",
        ),
    ]
