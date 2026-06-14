from seeders.base import BaseSeeder
from domains.catalog.models import  CategoryStatus
from domains.catalog.enums.CategoryStatusEnum import CategoryStatusEnum
class CategorySeeder(BaseSeeder):
    def run(self):
        # Create category statuses
        for status in CategoryStatusEnum:
            CategoryStatus.objects.update_or_create(
                id=status.value,
                defaults={
                    "name": status.name.lower()  # or status.name
                }
            )


        
