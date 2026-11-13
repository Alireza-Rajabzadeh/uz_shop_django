from core.management.seeders.base import BaseSeeder
from domains.business_payments.enums import BusinessPaymentStatusEnum
from domains.business_payments.models import BusinessPaymentStatus


class BusinessPaymentStatusSeeder(BaseSeeder):
    METADATA = {
        BusinessPaymentStatusEnum.PENDING: {
            "title": "در انتظار پرداخت",
            "description": "در انتظار پرداخت",
            "is_active": True,
        },
        BusinessPaymentStatusEnum.SUCCESSFUL: {
            "title": "پرداخت موفق",
            "description": "پرداخت موفق",
            "is_active": True,
        },
        BusinessPaymentStatusEnum.FAILED: {
            "title": "پرداخت ناموفق",
            "description": "پرداخت ناموفق",
            "is_active": True,
        },
    }

    @property
    def STATUSES(self):
        return [(e.name.lower(), self.METADATA[e]["title"]) for e in BusinessPaymentStatusEnum]

    def run(self):
        for status_enum, meta in self.METADATA.items():
            BusinessPaymentStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "name": status_enum.name.lower(),
                    "title": meta["title"],
                    "description": meta.get("description", ""),
                    "is_active": meta.get("is_active", True),
                },
            )
        self.sync_sequence(BusinessPaymentStatus)
