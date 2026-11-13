from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.management.seeders.configs import (
    CONFIG_SEEDERS,
    CONFIG_SEEDERS_MAP,
    get_config_seeder,
)


class Command(BaseCommand):
    help = "Run configuration and reference data seeders (or a specific config seeder by name)."

    def add_arguments(self, parser):
        parser.add_argument(
            "seeder",
            nargs="?",
            default=None,
            help=(
                "Optional name of a specific config seeder to run "
                f"({', '.join(sorted(CONFIG_SEEDERS_MAP.keys()))}). "
                "If omitted, all configuration seeders are run."
            ),
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all available configuration seeders and exit.",
        )
        parser.add_argument(
            "--fake",
            action="store_true",
            help="Also run development / fake data seeders after configuration seeders.",
        )

    def handle(self, *args, **options):
        if options.get("list"):
            self.stdout.write("Available configuration seeders:")
            for name in sorted(CONFIG_SEEDERS_MAP.keys()):
                cls_name = CONFIG_SEEDERS_MAP[name].__name__
                self.stdout.write(f"  - {name:<32} ({cls_name})")
            return

        target_name = options.get("seeder")
        if target_name:
            if target_name.lower() in ("list", "help"):
                self.stdout.write("Available configuration seeders:")
                for name in sorted(CONFIG_SEEDERS_MAP.keys()):
                    cls_name = CONFIG_SEEDERS_MAP[name].__name__
                    self.stdout.write(f"  - {name:<32} ({cls_name})")
                return

            seeder_cls = get_config_seeder(target_name)
            if not seeder_cls:
                available = ", ".join(sorted(CONFIG_SEEDERS_MAP.keys()))
                raise CommandError(
                    f"Unknown configuration seeder '{target_name}'.\n"
                    f"Available seeders: {available}"
                )

            self.stdout.write(f"Running {seeder_cls.__name__}...")
            seeder_cls().run()
            self.stdout.write(
                self.style.SUCCESS(f"{seeder_cls.__name__} completed successfully.")
            )
        else:
            self.stdout.write("Running all configuration seeders...")
            for seeder_cls in CONFIG_SEEDERS:
                self.stdout.write(f"Running {seeder_cls.__name__}...")
                seeder_cls().run()
            self.stdout.write(
                self.style.SUCCESS("Configuration seeding completed successfully.")
            )

        if options.get("fake"):
            self.stdout.write("Running fake development seeders...")
            call_command("seed_fake")
