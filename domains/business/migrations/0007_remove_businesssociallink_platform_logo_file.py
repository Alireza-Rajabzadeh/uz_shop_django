from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("business", "0006_socialmedia_socialmediaicon_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="businesssociallink",
            name="platform",
        ),
        migrations.RemoveField(
            model_name="businesssociallink",
            name="logo_file",
        ),
    ]
