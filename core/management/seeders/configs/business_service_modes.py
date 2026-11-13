from core.management.seeders.base import BaseSeeder
from domains.business.enums import BusinessServiceModeEnum
from domains.business.models import BusinessServiceMode


class BusinessServiceModeSeeder(BaseSeeder):
    """Idempotent seed for the business service-mode vocabulary using BusinessServiceModeEnum."""

    MODES = {
        BusinessServiceModeEnum.ONLINE: {
            "name": "Online",
            "description": "The business serves its customers online.",
            "is_active": True,
        },
        BusinessServiceModeEnum.IN_PERSON: {
            "name": "In Person",
            "description": "The business serves its customers in person.",
            "is_active": True,
        },
    }

    def run(self):
        for mode_enum, defaults in self.MODES.items():
            BusinessServiceMode.objects.update_or_create(
                id=mode_enum.value,
                defaults={
                    "code": mode_enum.code,
                    **defaults,
                },
            )
        self.sync_sequence(BusinessServiceMode)
