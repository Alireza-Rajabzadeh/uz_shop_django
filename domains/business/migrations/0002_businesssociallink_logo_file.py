from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("business", "0001_initial"),
        ("files", "0002_file_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="businesssociallink",
            name="logo_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="business_social_links",
                to="files.file",
            ),
        ),
    ]
