"""Attribute applied-price history to a business.

``VariantPriceHistory`` is the SQL audit of the cost-basis pricing flow. It was
keyed on the variant alone, so once a variant can carry a ``BusinessOffer`` per
business (``marketplace`` unique on ``(business, variant)``), two businesses
applying a price wrote indistinguishable rows. Pricing is single-business, so
the history now names its owner.

Existing rows predate multi-business support and belong to the original
singleton business (``id=1``). The column is added nullable, backfilled, then
tightened to ``NOT NULL`` so the invariant holds for every caller.

Reverse is a no-op: the pre-existing ``NULL`` is not recoverable, and re-nulling
would only re-break the invariant the next operation enforces.
"""

from django.db import migrations, models
import django.db.models.deletion


def _ensure_business_profile(apps):
    """Create BusinessProfile id=1 if it does not exist."""
    BusinessProfile = apps.get_model("business", "BusinessProfile")
    business, _ = BusinessProfile.objects.get_or_create(
        id=1,
        defaults={
            "business_name": "Migrated Business",
            "display_name": "Migrated",
        },
    )
    return business


def forwards(apps, schema_editor):
    business = _ensure_business_profile(apps)
    VariantPriceHistory = apps.get_model("inventory", "VariantPriceHistory")
    updated = VariantPriceHistory.objects.filter(business__isnull=True).update(
        business=business
    )
    print(
        f"  Backfilled price-history business: {updated} rows -> business #{business.id}"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0036_remove_stale_contenttype_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="variantpricehistory",
            name="business",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="variant_price_history",
                to="business.businessprofile",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="variantpricehistory",
            name="business",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="variant_price_history",
                to="business.businessprofile",
            ),
        ),
    ]
