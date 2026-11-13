from core.management.seeders.base import BaseSeeder
from domains.catalog.enums import ProductVariantStatusEnum
from domains.catalog.models import ProductVariantStatus


class ProductVariantStatusSeeder(BaseSeeder):
    def run(self):
        for status_enum in ProductVariantStatusEnum:
            name = status_enum.code
            status = ProductVariantStatus.objects.filter(name__iexact=name).first()
            if status is None:
                if not ProductVariantStatus.objects.filter(id=status_enum.value).exists():
                    ProductVariantStatus.objects.create(id=status_enum.value, name=name)
                else:
                    ProductVariantStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
        self.sync_sequence(ProductVariantStatus)
