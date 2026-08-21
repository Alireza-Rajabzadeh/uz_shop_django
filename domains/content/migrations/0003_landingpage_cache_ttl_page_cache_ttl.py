from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0002_page")]

    operations = [
        migrations.AddField(
            model_name="landingpage",
            name="cache_ttl",
            field=models.PositiveIntegerField(default=300),
        ),
        migrations.AddField(
            model_name="page",
            name="cache_ttl",
            field=models.PositiveIntegerField(default=300),
        ),
    ]
