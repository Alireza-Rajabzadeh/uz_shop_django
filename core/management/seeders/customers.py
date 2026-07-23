from core.management.seeders.base import BaseSeeder
from domains.customer.models import CustomerStatus
from domains.customer.enums.CustomerStatusEnum import CustomerStatusEnum


class CustomerSeeder(BaseSeeder):
    def run(self):
        statuses = {
            CustomerStatusEnum.ACTIVE: {
                "title": "Active",
                "description": "Active customer account",
                "is_active": True,
            },
            CustomerStatusEnum.INACTIVE: {
                "title": "Inactive",
                "description": "Inactive customer account",
                "is_active": False,
            },
            CustomerStatusEnum.PENDING: {
                "title": "Pending",
                "description": "Pending customer account",
                "is_active": False,
            },
            CustomerStatusEnum.BANNED: {
                "title": "Banned",
                "description": "Banned customer account",
                "is_active": False,
            },
        }

        for status_enum, data in statuses.items():
            CustomerStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "name": status_enum.name.lower(),
                    "title": data["title"],
                    "description": data["description"],
                    "is_active": data["is_active"],
                },
            )
