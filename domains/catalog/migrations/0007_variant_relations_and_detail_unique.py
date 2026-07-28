from django.db import migrations, models
from django.db.models import Count, Max


def remove_duplicate_variant_details(apps, schema_editor):
    VariantDetail = apps.get_model("catalog", "ProductVariantsDetails")
    duplicates = (
        VariantDetail.objects.values("variant_id", "detail_id")
        .annotate(keep_id=Max("id"), row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by()
    )
    for duplicate in duplicates:
        VariantDetail.objects.filter(
            variant_id=duplicate["variant_id"],
            detail_id=duplicate["detail_id"],
        ).exclude(id=duplicate["keep_id"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_ensure_pending_product_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productvariants",
            name="product",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="variants",
                to="catalog.product",
            ),
        ),
        migrations.AlterField(
            model_name="productvariantsdetails",
            name="variant",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="details",
                to="catalog.productvariants",
            ),
        ),
        migrations.RunPython(
            remove_duplicate_variant_details,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="productvariantsdetails",
            constraint=models.UniqueConstraint(
                fields=("variant", "detail"),
                name="catalog_variant_detail_unique",
            ),
        ),
    ]
