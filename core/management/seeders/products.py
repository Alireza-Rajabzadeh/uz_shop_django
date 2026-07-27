import random

from core.management.seeders.base import BaseSeeder
from domains.catalog.models import Category, Product, ProductStatus


class ProductSeeder(BaseSeeder):
    def run(self):
        statuses = []
        for status_id, name in enumerate(("active", "inactive", "pending"), start=1):
            status, _ = ProductStatus.objects.update_or_create(
                id=status_id,
                defaults={"name": name},
            )
            statuses.append(status)

        categories = list(
            Category.objects.filter(name__startswith="Test Category ").order_by("name")
        )
        if not categories:
            raise RuntimeError("Test categories must be seeded before test products.")

        randomizer = random.Random(84)
        for index in range(1, 101):
            Product.objects.update_or_create(
                name=f"Test Product {index:03d}",
                defaults={
                    "category": randomizer.choice(categories),
                    "status": statuses[(index - 1) % len(statuses)],
                    "description": f"Temporary product {index:03d} for admin-panel development.",
                },
            )
