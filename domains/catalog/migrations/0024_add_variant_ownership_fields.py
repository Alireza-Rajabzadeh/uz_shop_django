from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


PENDING_STATUS = "wait_for_admin_confirmation"


def ensure_wait_for_admin_confirmation_variant_status(apps, schema_editor):
    """Add the review status vendor-created variants wait in.

    Mirrors 0006_ensure_pending_product_status: the row is reference data the
    write path looks up by name, so an existing database has to gain it
    without a full seed run.
    """
    ProductVariantStatus = apps.get_model("catalog", "ProductVariantStatus")
    matches = list(
        ProductVariantStatus.objects.filter(name__iexact=PENDING_STATUS).order_by("id")
    )
    if not matches:
        ProductVariantStatus.objects.create(name=PENDING_STATUS)
        return

    keeper = next(
        (status for status in matches if status.name == PENDING_STATUS), matches[0]
    )
    duplicate_ids = [status.id for status in matches if status.id != keeper.id]
    if duplicate_ids:
        ProductVariants = apps.get_model("catalog", "ProductVariants")
        ProductVariants.objects.filter(status_id__in=duplicate_ids).update(
            status_id=keeper.id
        )
        ProductVariantStatus.objects.filter(id__in=duplicate_ids).delete()
    if keeper.name != PENDING_STATUS:
        keeper.name = PENDING_STATUS
        keeper.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0023_add_vendor_creation_fields"),
        ("vendor", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariants",
            name="created_by_vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_variants",
                to="vendor.vendor",
            ),
        ),
        migrations.AddField(
            model_name="productvariants",
            name="creator_model",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="productvariants",
            name="confirmed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="confirmed_variants",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            ensure_wait_for_admin_confirmation_variant_status,
            migrations.RunPython.noop,
        ),
    ]
