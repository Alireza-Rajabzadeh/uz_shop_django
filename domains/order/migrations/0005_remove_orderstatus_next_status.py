from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0004_remove_orderstatus_available_actions"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="orderstatus",
            name="next_status",
        ),
    ]
