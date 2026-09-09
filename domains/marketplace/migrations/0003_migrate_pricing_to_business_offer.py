from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def forwards(apps, schema_editor):
    ProductVariants = apps.get_model("catalog", "ProductVariants")
    BusinessOffer = apps.get_model("marketplace", "BusinessOffer")
    BusinessProfile = apps.get_model("business", "BusinessProfile")

    business = BusinessProfile.objects.first()
    if business is None:
        return

    variants = ProductVariants.objects.filter(
        Q(price__gt=0) | Q(discount_type__isnull=False)
    )

    for variant in variants:
        offer, created = BusinessOffer.objects.get_or_create(
            business=business,
            variant=variant,
            defaults={
                "price": variant.price or Decimal("0"),
                "discount_type": variant.discount_type,
                "discount_value": variant.discount_value,
            },
        )
        if not created:
            offer.price = variant.price or Decimal("0")
            offer.discount_type = variant.discount_type
            offer.discount_value = variant.discount_value
            offer.save(update_fields=["price", "discount_type", "discount_value"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("business", "0003_businessprofile_dark_logo_and_more"),
        ("marketplace", "0002_add_pricing_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
