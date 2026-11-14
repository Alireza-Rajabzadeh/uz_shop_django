from core.management.seeders.base import BaseSeeder
from domains.business.enums import BusinessSubdomainEnum
from domains.business.models import BusinessSubdomainStatus


class BusinessSubdomainStatusSeeder(BaseSeeder):
    """Idempotent seeder for business subdomain status reference rows using BusinessSubdomainEnum."""

    METADATA = {
        BusinessSubdomainEnum.ACTIVE: {
            "code": "active",
            "name": "Active",
            "title": "فعال",
        },
        BusinessSubdomainEnum.REDIRECT: {
            "code": "redirect",
            "name": "Redirect",
            "title": "هدایت شونده",
        },
        BusinessSubdomainEnum.RESERVED: {
            "code": "reserved",
            "name": "Reserved",
            "title": "رزرو شده",
        },
    }

    def run(self):
        for status_enum, meta in self.METADATA.items():
            BusinessSubdomainStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "code": meta["code"],
                    "name": meta["name"],
                    "title": meta["title"],
                },
            )
        self.sync_sequence(BusinessSubdomainStatus)
