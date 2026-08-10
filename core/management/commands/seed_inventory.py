import random

from django.core.management.base import BaseCommand

from domains.catalog.models import ProductVariants
from domains.inventory.services import InventoryService


class Command(BaseCommand):
    help = (
        "Idempotently provision test inventory for every product variant in the "
        "default warehouse. Normal variants get a deterministic quantity; "
        "serialized variants get sellable serial units when they have none."
    )

    def handle(self, *args, **options):
        service = InventoryService()
        variants = ProductVariants.objects.select_related("inventory_strategy").order_by("id")
        normal_count = 0
        serialized_count = 0
        for variant in variants:
            code = variant.inventory_strategy.code
            if code == "normal":
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
                normal_count += 1
            elif code == "serialized" and not variant.serialized_stocks.exists():
                rng = random.Random(variant.id)
                count = rng.randint(3, 12)
                self._create_serialized(service, variant, count)
                serialized_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded inventory for {normal_count} normal and "
                f"{serialized_count} serialized variants "
                f"({variants.count()} total)."
            )
        )

    def _create_serialized(self, service, variant, count):
        from domains.inventory.models import SerializedStock, SerializedStockStatus

        warehouse = service.get_default_warehouse(lock=True)
        in_stock = SerializedStockStatus.objects.filter(code="in_stock").first()
        if in_stock is None:
            raise RuntimeError("Serialized stock statuses are not seeded.")
        SerializedStock.objects.bulk_create(
            SerializedStock(
                variant=variant,
                warehouse=warehouse,
                status=in_stock,
                serial_number=f"{variant.sku}-{i:04d}",
                sellable=True,
                reserved=False,
            )
            for i in range(1, count + 1)
        )
