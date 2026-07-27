from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_category_detail_normalized_name_and_options"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="productdetails",
            constraint=models.UniqueConstraint(
                fields=("product", "detail"),
                name="catalog_product_detail_unique",
            ),
        ),
    ]
