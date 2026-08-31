from core.management.seeders.base import BaseSeeder
from domains.catalog.models import ProductVariantStatus


class ProductVariantStatusSeeder(BaseSeeder):
    def run(self):
        for name in ("active", "inactive", "pending"):
            status = ProductVariantStatus.objects.filter(name__iexact=name).first()
            if status is None:
                ProductVariantStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
