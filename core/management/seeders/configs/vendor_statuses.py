from core.management.seeders.base import BaseSeeder
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import VendorStatus


class VendorStatusSeeder(BaseSeeder):
    METADATA = {
        VendorStatusEnum.ACTIVE: {"title": "فعال", "is_active": True},
        VendorStatusEnum.INACTIVE: {"title": "غیرفعال", "is_active": False},
        VendorStatusEnum.PENDING: {"title": "در انتظار تایید", "is_active": False},
        VendorStatusEnum.BANNED: {"title": "مسدود", "is_active": False},
    }

    @property
    def STATUSES(self):
        return [(e.name.lower(), self.METADATA[e]["title"]) for e in VendorStatusEnum]

    def run(self):
        for status_enum, meta in self.METADATA.items():
            VendorStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "name": status_enum.name.lower(),
                    "title": meta["title"],
                    "is_active": meta["is_active"],
                },
            )
        self.sync_sequence(VendorStatus)
