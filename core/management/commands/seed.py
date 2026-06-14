from django.core.management.base import BaseCommand

from seeders.categories import CategorySeeder
from seeders.products import ProductSeeder


class Command(BaseCommand):
    help = "Run all seeders"

    def handle(self, *args, **kwargs):
        seeders = [
            CategorySeeder(),
            ProductSeeder(),
        ]

        for seeder in seeders:
            self.stdout.write(f"Running {seeder.__class__.__name__}...")
            seeder.run()

        self.stdout.write(self.style.SUCCESS("Seeding completed"))