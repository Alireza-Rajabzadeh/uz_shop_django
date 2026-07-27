from django.db import migrations, models
from django.db.models.functions import Lower, Trim


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_category_normalized_name_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="categorydetail",
            name="name",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="categorydetail",
            name="options",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddConstraint(
            model_name="categorydetail",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_category_detail_normalized_name_unique",
            ),
        ),
    ]
