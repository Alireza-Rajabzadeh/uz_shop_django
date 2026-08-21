from django.db import migrations, models
import django.db.models.deletion


def backfill_brand_categories(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    BrandCategory = apps.get_model("catalog", "BrandCategory")
    rows = (
        Product.objects.exclude(brand_id=None)
        .values_list("brand_id", "categories__id")
        .exclude(categories__id=None)
        .distinct()
    )
    BrandCategory.objects.bulk_create(
        [BrandCategory(brand_id=brand_id, category_id=category_id) for brand_id, category_id in rows],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0016_category_brand_slug_variant_attribute_fa_name")]

    operations = [
        migrations.CreateModel(
            name="BrandCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("brand", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="category_assignments", to="catalog.brand")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="brand_assignments", to="catalog.category")),
            ],
            options={"db_table": "catalog_brand_category"},
        ),
        migrations.AddConstraint(
            model_name="brandcategory",
            constraint=models.UniqueConstraint(fields=("brand", "category"), name="catalog_brand_category_unique"),
        ),
        migrations.AddField(
            model_name="brand",
            name="categories",
            field=models.ManyToManyField(blank=True, related_name="brands", through="catalog.BrandCategory", to="catalog.category"),
        ),
        migrations.RunPython(backfill_brand_categories, migrations.RunPython.noop),
    ]
