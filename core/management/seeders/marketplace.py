from core.management.seeders.base import BaseSeeder
from domains.marketplace.data.pricing_strategies import PRICING_STRATEGY_SEED
from domains.marketplace.models import PricingStrategy


class MarketplaceSeeder(BaseSeeder):
    def run(self):
        self._seed_pricing_strategies()

    def _seed_pricing_strategies(self):
        # Reference data only: vendors never write these rows, and adding a
        # strategy still requires code. Keeps `manage.py seed` idempotent for
        # databases that were migrated before a guide copy was edited.
        for row in PRICING_STRATEGY_SEED:
            PricingStrategy.objects.update_or_create(
                id=row["id"],
                defaults={key: value for key, value in row.items() if key != "id"},
            )
