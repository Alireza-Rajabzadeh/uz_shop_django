from core.management.seeders.base import BaseSeeder
from domains.business.enums import BusinessStatusEnum
from domains.business.models import BusinessStatus


class BusinessStatusSeeder(BaseSeeder):
    """Idempotent re-seed of the lifecycle reference rows using BusinessStatusEnum."""

    METADATA = {
        BusinessStatusEnum.ACTIVE: {
            "code": "active",
            "name": "Active",
            "title": "فعال",
        },
        BusinessStatusEnum.BANNED: {
            "code": "banned",
            "name": "Banned",
            "title": "مسدود",
        },
        BusinessStatusEnum.CONFIRMATION_AWAIT: {
            "code": "confirmation_await",
            "name": "Confirmation await",
            "title": "در انتظار تایید",
        },
    }

    def run(self):
        for status_enum, meta in self.METADATA.items():
            BusinessStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "code": meta["code"],
                    "name": meta["name"],
                    "title": meta["title"],
                },
            )
        self.sync_sequence(BusinessStatus)
