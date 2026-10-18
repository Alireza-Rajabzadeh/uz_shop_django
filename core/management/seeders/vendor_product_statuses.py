from core.management.seeders.base import BaseSeeder
from domains.catalog.models import VendorProductStatus


class VendorProductStatusSeeder(BaseSeeder):
    def run(self):
        # Insertion order is the display order in the admin review queue.
        for name in VendorProductStatus.Code.values:
            status = VendorProductStatus.objects.filter(name__iexact=name).first()
            if status is None:
                VendorProductStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
