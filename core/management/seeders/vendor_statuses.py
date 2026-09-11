from core.management.seeders.base import BaseSeeder
from domains.vendor.models import VendorStatus


class VendorStatusSeeder(BaseSeeder):
    STATUSES = [
        ("active", "فعال"),
        ("inactive", "غیرفعال"),
        ("pending", "در انتظار تایید"),
        ("banned", "مسدود"),
    ]

    def run(self):
        for name, title in self.STATUSES:
            VendorStatus.objects.get_or_create(
                name=name,
                defaults={"title": title, "is_active": name == "active"},
            )
