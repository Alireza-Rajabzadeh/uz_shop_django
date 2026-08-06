from django.db import migrations, models
from django.db.models.functions import Lower, Trim


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_product_slug"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="category",
            name="catalog_category_normalized_name_unique",
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                Lower(Trim("name")),
                condition=models.Q(parent__isnull=True),
                name="catalog_root_category_normalized_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                models.F("parent"),
                Lower(Trim("name")),
                condition=models.Q(parent__isnull=False),
                name="catalog_child_category_normalized_name_unique",
            ),
        ),
    ]
