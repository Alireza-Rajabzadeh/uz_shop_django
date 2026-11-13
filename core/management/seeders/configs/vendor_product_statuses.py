from core.management.seeders.base import BaseSeeder
from domains.catalog.enums import VendorProductStatusEnum
from domains.catalog.models import VendorProductStatus


class VendorProductStatusSeeder(BaseSeeder):
    def run(self):
        for status_enum in VendorProductStatusEnum:
            name = status_enum.code
            status = VendorProductStatus.objects.filter(name__iexact=name).first()
            if status is None:
                if not VendorProductStatus.objects.filter(id=status_enum.value).exists():
                    VendorProductStatus.objects.create(id=status_enum.value, name=name)
                else:
                    VendorProductStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
        self.sync_sequence(VendorProductStatus)
