from django.core.management.base import BaseCommand

from core.management.seeders.categories import CategorySeeder
from core.management.seeders.inventory import InventorySeeder
from core.management.seeders.products import ProductSeeder
from core.management.seeders.customers import CustomerSeeder
from core.management.seeders.location import LocationSeeder
from core.management.seeders.variant_attributes import VariantAttributeSeeder


class Command(BaseCommand):
    help = "Run all seeders"

    def handle(self, *args, **kwargs):
        seeders = [
            LocationSeeder(),
            CategorySeeder(),
            VariantAttributeSeeder(),
            ProductSeeder(),
            InventorySeeder(),
            CustomerSeeder(),
        ]

        for seeder in seeders:
            self.stdout.write(f"Running {seeder.__class__.__name__}...")
            seeder.run()

        self.stdout.write(self.style.SUCCESS("Seeding completed"))
