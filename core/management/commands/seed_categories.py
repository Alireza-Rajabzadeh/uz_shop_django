from django.core.management.base import BaseCommand

from core.management.seeders.categories import CategorySeeder


class Command(BaseCommand):
    help = "Seed the canonical category taxonomy without deleting existing categories"

    def handle(self, *args, **options):
        count = CategorySeeder().run()
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} canonical categories"))
