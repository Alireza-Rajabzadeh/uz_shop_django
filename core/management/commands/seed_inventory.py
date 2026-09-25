import random

from django.core.management.base import BaseCommand

from domains.catalog.models import ProductVariants
from domains.inventory.models import Inventory
from domains.inventory.services import InventoryService


class Command(BaseCommand):
    help = (
        "Idempotently provision test inventory for every product variant in the "
        "default warehouse. Variants with existing stock are skipped. "
        "Variants without stock get a deterministic quantity of normal inventory."
    )

    def handle(self, *args, **options):
        service = InventoryService()
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
            )
            count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded inventory for {count} variants "
                f"({variants.count()} total)."
            )
        )
