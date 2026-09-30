from django.db import migrations, models
import django.db.models.deletion

from domains.marketplace.data.pricing_strategies import PRICING_STRATEGY_SEED


def seed_pricing_strategies(apps, schema_editor):
    """Insert the three system-defined cost strategies with fixed ids.

    Id 1 is `latest` because BusinessOffer.cost_strategy defaults to it.
    """
    PricingStrategy = apps.get_model("marketplace", "PricingStrategy")
    PricingStrategy.objects.bulk_create(
        [
            PricingStrategy(
                id=row["id"],
                code=row["code"],
                name=row["name"],
                fa_name=row["fa_name"],
                description=row["description"],
            )
            for row in PRICING_STRATEGY_SEED
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0006_offerpricehistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="PricingStrategy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("fa_name", models.CharField(max_length=100)),
                ("description", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "marketplace_pricing_strategy",
                "ordering": ["id"],
            },
        ),
        migrations.RunPython(
            seed_pricing_strategies, reverse_code=migrations.RunPython.noop
        ),
        # cost_strategy was a varchar holding a code. Dropping it and adding
        # the FK column resets every existing offer to the `latest` default —
        # intentional: the rows are dev data and the strategy is re-selectable
        # from the panel. Audit tables (OfferPriceHistory, VariantPriceHistory)
        # keep their own varchar snapshots of the code.
        migrations.RemoveField(
            model_name="businessoffer",
            name="cost_strategy",
        ),
        migrations.AddField(
            model_name="businessoffer",
            name="cost_strategy",
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="offers",
                to="marketplace.pricingstrategy",
            ),
        ),
    ]
