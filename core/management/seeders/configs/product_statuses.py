from core.management.seeders.base import BaseSeeder
from domains.catalog.enums import ProductStatusEnum
from domains.catalog.models import ProductStatus


class ProductStatusSeeder(BaseSeeder):
    def run(self):
        for status_enum in ProductStatusEnum:
            name = status_enum.code
            status = ProductStatus.objects.filter(name__iexact=name).first()
            if status is None:
                if not ProductStatus.objects.filter(id=status_enum.value).exists():
                    ProductStatus.objects.create(id=status_enum.value, name=name)
                else:
                    ProductStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
        self.sync_sequence(ProductStatus)
