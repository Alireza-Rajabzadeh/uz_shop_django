from django.core.management.base import BaseCommand

from domains.inventory.services.inventory_service import InventoryService


class Command(BaseCommand):
    help = (
        "Delete inventory units left in the changed_type state by a "
        "serialized -> normal conversion once they pass the retention window. "
        "Run manually; there is no beat schedule for it."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=90,
            help="Retention window in days (default: 90).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the number of matching units without deleting them.",
        )

    def handle(self, *args, **options):
        deleted = InventoryService().purge_changed_type_units(
            older_than_days=options["older_than_days"],
            dry_run=options["dry_run"],
        )
        verb = "would delete" if options["dry_run"] else "deleted"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {deleted} changed_type unit(s)")
        )
