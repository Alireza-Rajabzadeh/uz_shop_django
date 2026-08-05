from django.db import migrations, models
from django.utils.text import slugify


def populate_product_slugs(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    used = set(Product.objects.exclude(slug__isnull=True).values_list("slug", flat=True))
    for product in Product.objects.order_by("id").iterator():
        base = slugify(product.name, allow_unicode=True)[:250] or "product"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base[:270 - len(str(suffix))]}-{suffix}"
            suffix += 1
        used.add(candidate)
        Product.objects.filter(pk=product.pk).update(slug=candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_storefront_search_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="slug",
            field=models.SlugField(
                editable=False,
                max_length=280,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(populate_product_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="slug",
            field=models.SlugField(editable=False, max_length=280, unique=True),
        ),
    ]
