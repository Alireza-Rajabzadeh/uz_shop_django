from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_variant_relations_and_detail_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productvariantsdetails",
            name="variant",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="details",
                to="catalog.productvariants",
            ),
        ),
    ]
