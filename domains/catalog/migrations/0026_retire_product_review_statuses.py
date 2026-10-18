"""Retire the product-level review statuses.

`wait_for_admin_confirmation` and `admin_rejected` used to describe a product
sitting in front of an admin. That flow moved to vendor submissions
(`catalog_vendor_product*`), so neither name belongs in `catalog_product_status`
anymore and `ProductStatusEnum` no longer lists them.

Only the *product* vocabulary changes here: the identically named
`ProductVariantStatus` entry is still live and is untouched. Nothing in this
migration deletes a product — a product still parked on a retired status is
re-homed to `pending` so the row stays intact and simply awaits normal catalog
work again.
"""

from django.db import migrations

RETIRED_STATUSES = ("wait_for_admin_confirmation", "admin_rejected")
REPLACEMENT_STATUS = "pending"


def retire_product_review_statuses(apps, schema_editor):
    ProductStatus = apps.get_model("catalog", "ProductStatus")
    Product = apps.get_model("catalog", "Product")

    retired_ids = list(
        ProductStatus.objects.filter(name__in=RETIRED_STATUSES).values_list(
            "id", flat=True
        )
    )
    if not retired_ids:
        return

    replacement, _ = ProductStatus.objects.get_or_create(name=REPLACEMENT_STATUS)
    Product.objects.filter(status_id__in=retired_ids).update(status=replacement)
    ProductStatus.objects.filter(id__in=retired_ids).delete()


def restore_product_review_statuses(apps, schema_editor):
    # The old product rows cannot be told apart from genuinely pending ones, so
    # only the vocabulary is restored; re-running the forward migration will
    # retire it again.
    ProductStatus = apps.get_model("catalog", "ProductStatus")
    for name in RETIRED_STATUSES:
        ProductStatus.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0025_vendor_product_submission_tables"),
    ]

    operations = [
        migrations.RunPython(
            retire_product_review_statuses,
            restore_product_review_statuses,
        ),
    ]
