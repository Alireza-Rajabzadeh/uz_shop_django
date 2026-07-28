from django.db import migrations


def ensure_pending_product_status(apps, schema_editor):
    ProductStatus = apps.get_model("catalog", "ProductStatus")
    Product = apps.get_model("catalog", "Product")
    matches = list(ProductStatus.objects.filter(name__iexact="pending").order_by("id"))
    if not matches:
        ProductStatus.objects.create(name="pending")
        return

    keeper = next((status for status in matches if status.name == "pending"), matches[0])
    duplicate_ids = [status.id for status in matches if status.id != keeper.id]
    if duplicate_ids:
        Product.objects.filter(status_id__in=duplicate_ids).update(status_id=keeper.id)
        ProductStatus.objects.filter(id__in=duplicate_ids).delete()
    if keeper.name != "pending":
        keeper.name = "pending"
        keeper.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_product_detail_unique"),
    ]

    operations = [
        migrations.RunPython(ensure_pending_product_status, migrations.RunPython.noop),
    ]
