from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_sentnotification_is_sensitive")]

    operations = [
        migrations.AddField(
            model_name="sentnotification",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
