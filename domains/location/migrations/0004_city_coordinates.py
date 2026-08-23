from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("location", "0003_location_normalized_constraints")]

    operations = [
        migrations.AddField(
            model_name="city",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=10, null=True
            ),
        ),
        migrations.AddField(
            model_name="city",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=10, null=True
            ),
        ),
    ]
