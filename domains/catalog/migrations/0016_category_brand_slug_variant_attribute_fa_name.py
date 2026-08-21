from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    specs = (
        ("Category", "category", 100),
        ("Brand", "brand", 150),
    )
    for model_name, fallback, max_length in specs:
        model = apps.get_model("catalog", model_name)
        used = set(model.objects.exclude(slug__isnull=True).values_list("slug", flat=True))
        for instance in model.objects.order_by("id").iterator():
            base = slugify(instance.name, allow_unicode=True)[:max_length - 30] or fallback
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base[:max_length - 10 - len(str(suffix))]}-{suffix}"
                suffix += 1
            used.add(candidate)
            model.objects.filter(pk=instance.pk).update(slug=candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_variant_option_info"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="slug",
            field=models.SlugField(editable=False, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="brand",
            name="slug",
            field=models.SlugField(editable=False, max_length=150, null=True, unique=True),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="category",
            name="slug",
            field=models.SlugField(editable=False, max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name="brand",
            name="slug",
            field=models.SlugField(editable=False, max_length=150, unique=True),
        ),
        migrations.AddField(
            model_name="variantattribute",
            name="fa_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
