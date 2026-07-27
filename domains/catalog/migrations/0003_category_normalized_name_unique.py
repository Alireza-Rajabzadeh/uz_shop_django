from django.db import migrations, models
from django.db.models.functions import Lower, Trim


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_alter_category_options_alter_product_options"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")),
                name="catalog_category_normalized_name_unique",
            ),
        ),
    ]
