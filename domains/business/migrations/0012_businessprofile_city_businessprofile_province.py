import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("business", "0011_businessstatus"),
        ("location", "0005_populate_city_coordinates"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="province",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="business_profiles",
                to="location.state",
            ),
        ),
        migrations.AddField(
            model_name="businessprofile",
            name="city",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="business_profiles",
                to="location.city",
            ),
        ),
    ]
