import random

from core.management.seeders.base import BaseSeeder
from domains.business.models import BusinessProfile
from domains.catalog.models import ProductVariants
from domains.inventory.models import Inventory
from domains.inventory.services import InventoryService


class InventoryStockSeeder(BaseSeeder):
    """Idempotently provision test inventory for every product variant in the default warehouse."""

    def run(self):
        service = InventoryService()
        business = BusinessProfile.objects.filter(id=1).first()
        variants = ProductVariants.objects.order_by("id")
        count = 0
        for variant in variants:
            has_stock = Inventory.objects.filter(variant=variant).exists()
            if has_stock:
                continue
            rng = random.Random(variant.id)
            quantity = rng.randint(6, 50)
            min_stock = max(0, min(quantity, rng.randint(2, 8)))
            service.adjust_variant_stock(
                variant,
                inventory={
                    "quantity": quantity,
                    "sellable": quantity,
                    "reserved": 0,
                    "min_stock": min_stock,
                },
                business=business,
            )
            count += 1
        return count
