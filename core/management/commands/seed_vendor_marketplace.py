from django.core.management.base import BaseCommand

from core.management.data.vendor_marketplace_fixtures import SHARED_PASSWORD
from core.management.seeders.vendor_marketplace_fixtures import (
    VendorMarketplaceSeeder,
)


class Command(BaseCommand):
    help = (
        "Create development vendors, one complete business per vendor, their "
        "category assignments, inventory supplies, and marketplace offers. "
        "Idempotent; re-running converges the same fixture set."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--vendors",
            type=int,
            default=100,
            help="Number of fixture vendors to create (default: 100).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=20261022,
            help="Deterministic random seed (default: 20261022).",
        )

    def handle(self, *args, **options):
        seeder = VendorMarketplaceSeeder(
            vendor_count=options["vendors"],
            seed=options["seed"],
        )
        counts = seeder.run()

        self.stdout.write(
            self.style.SUCCESS(
                "Vendor marketplace fixtures ready: "
                f"{counts['vendors_created']} vendors, "
                f"{counts['businesses_created']} businesses, "
                f"{counts['products_created']} products, "
                f"{counts['variants_created']} variants, "
                f"{counts['warehouses_created']} warehouses, "
                f"{counts['supplies_created']} supplies, "
                f"{counts['offers_created']} offers created."
            )
        )
        self.stdout.write(
            f"Fixture vendor password: {SHARED_PASSWORD} "
            "(phones are 09900000001 ... by index)."
        )
