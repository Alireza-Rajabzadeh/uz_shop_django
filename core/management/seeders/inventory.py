from core.management.seeders.base import BaseSeeder
from domains.inventory.models import InventoryType, Warehouse, WarehouseStatus
from domains.inventory.enums.InventoryTypeEnum import InventoryTypeEnum
from domains.inventory.enums.WarehouseStatusEnum import WarehouseStatusEnum
from domains.location.models import City


class InventorySeeder(BaseSeeder):
    def run(self):
        self._seed_inventory_types()
        self._seed_warehouse_statuses()
        self._seed_default_warehouse()

    def _seed_inventory_types(self):
        values = {
            InventoryTypeEnum.NORMAL.value: {
                "code": "normal",
                "name": "Normal",
                "fa_name": "عادی",
                "description": "Quantity-based inventory without per-unit serial tracking.",
            },
            InventoryTypeEnum.SERIALIZED.value: {
                "code": "serialized",
                "name": "Serialized",
                "fa_name": "سریالی",
                "description": "Inventory tracked as individually registered units.",
            },
        }
        for inventory_type_id, defaults in values.items():
            InventoryType.objects.update_or_create(
                id=inventory_type_id,
                defaults=defaults,
            )

    def _seed_warehouse_statuses(self):
        for status in WarehouseStatusEnum:
            WarehouseStatus.objects.update_or_create(
                id=status.value,
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
