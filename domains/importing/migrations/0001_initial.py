from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0016_category_brand_slug_variant_attribute_fa_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalProductIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=50)),
                ("external_id", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="external_identities", to="catalog.product")),
            ],
            options={"db_table": "importing_external_product_identity"},
        ),
        migrations.AddConstraint(
            model_name="externalproductidentity",
            constraint=models.UniqueConstraint(fields=("provider", "external_id"), name="importing_provider_external_product_uniq"),
        ),
    ]
