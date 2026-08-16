from django.core.management.base import BaseCommand
from django.db.models import Q

from domains.catalog.category_icons import match_category_icon
from domains.catalog.models import Category


class Command(BaseCommand):
    help = "Assign stable visual icon keys to categories based on their names"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report matches without updating categories.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace icons already assigned to categories.",
        )

    def handle(self, *args, **options):
        queryset = Category.objects.order_by("id")
        if not options["overwrite"]:
            queryset = queryset.filter(Q(logo__isnull=True) | Q(logo=""))

        matched = []
        unmatched = 0
        for category in queryset:
            icon = match_category_icon(category.name, category.fa_name)
            if icon:
                category.logo = icon
                matched.append(category)
            else:
                unmatched += 1

        if matched and not options["dry_run"]:
            Category.objects.bulk_update(matched, ["logo"])

        action = "Would assign" if options["dry_run"] else "Assigned"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} icons to {len(matched)} categories; "
                f"left {unmatched} unmatched categories unchanged."
            )
        )
