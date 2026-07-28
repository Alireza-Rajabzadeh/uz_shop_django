from core.management.seeders.base import BaseSeeder
from domains.inventory.models import (
    InventoryStrategy,
    Warehouse,
    WarehouseStatus,
    SerializedStockStatus,
)
from domains.inventory.enums.InventoryStrategyEnum import InventoryStrategyEnum
from domains.inventory.enums.WarehouseStatusEnum import WarehouseStatusEnum
from domains.inventory.enums.SerializedStockStatusEnum import SerializedStockStatusEnum
from domains.location.models import City


class InventorySeeder(BaseSeeder):
    def run(self):
        self._seed_strategies()
        self._seed_warehouse_statuses()
        self._seed_serialized_stock_statuses()
        self._seed_default_warehouse()

    def _seed_strategies(self):
        strategies = {
            InventoryStrategyEnum.NORMAL: {
                "name": "Normal",
                "description": "Stock tracked by variant quantity (aggregate count). Used for products like T-shirts where variants (color/size) define stock levels.",
            },
            InventoryStrategyEnum.SERIALIZED: {
                "name": "Serialized",
                "description": "Each unit tracked by unique serial number. Used for products like mobile phones where each item has a unique identifier.",
            },
        }

        for code, data in strategies.items():
            InventoryStrategy.objects.update_or_create(
                code=code.value,
                defaults={
                    "name": data["name"],
                    "description": data["description"],
                },
            )

    def _seed_warehouse_statuses(self):
        for status in WarehouseStatusEnum:
            WarehouseStatus.objects.update_or_create(
                id=status.value,
                defaults={"name": status.name.lower()},
            )

    def _seed_serialized_stock_statuses(self):
        for status in SerializedStockStatusEnum:
            SerializedStockStatus.objects.update_or_create(
                code=status.name.lower(),
                defaults={"name": status.name.lower()},
            )

    def _seed_default_warehouse(self):
        city = City.objects.order_by("id").first()
        if city is None:
            raise RuntimeError("Seed location data before creating the default warehouse.")
        available = WarehouseStatus.objects.get(id=WarehouseStatusEnum.AVAILABLE.value)
        Warehouse.objects.filter(is_default=True).exclude(code="WH-00001").update(is_default=False)
        Warehouse.objects.update_or_create(
            code="WH-00001",
            defaults={
                "name": "Warehouse Tehran",
                "city": city,
                "address": "Tehran, Iran",
                "lat": "35.689200",
                "lng": "51.389000",
                "phone_numbers": ["021-12345678", "0912-345-6789"],
                "postal_code": "158756413",
                "is_default": True,
                "status": available,
            },
        )
