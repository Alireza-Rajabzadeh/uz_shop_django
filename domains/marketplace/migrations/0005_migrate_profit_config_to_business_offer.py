from django.db import migrations


def forwards(apps, schema_editor):
    BusinessOffer = apps.get_model("marketplace", "BusinessOffer")
    VariantPricing = apps.get_model("inventory", "VariantPricing")

    pricing_map = {
        vp.variant_id: vp
        for vp in VariantPricing.objects.all()
    }

    for offer in BusinessOffer.objects.all():
        vp = pricing_map.get(offer.variant_id)
        if vp is not None:
            offer.expected_profit_percentage = vp.expected_profit_percentage
            offer.cost_strategy = vp.cost_strategy
            offer.save(update_fields=["expected_profit_percentage", "cost_strategy"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0004_businessoffer_pricing_config"),
        ("inventory", "0012_variantpricing"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
