from django.core.management.base import BaseCommand, CommandError

from core.management.seeders.configs import CONFIG_SEEDERS
from core.management.seeders.developing import (
    BusinessPaymentChannelsSeeder,
    CustomerSeeder,
    DEVELOPING_SEEDERS_MAP,
    InventoryStockSeeder,
    VendorMarketplaceSeeder,
    get_developing_seeder,
)


class Command(BaseCommand):
    help = (
        "Run development seeders to generate fake data "
        "(customers, vendors, marketplace fixtures, inventory stock, payment channels), "
        "or run a specific fake seeder by name with custom arguments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "seeder",
            nargs="?",
            default=None,
            help=(
                "Optional name of a specific fake seeder to run "
                f"({', '.join(sorted(DEVELOPING_SEEDERS_MAP.keys()))}, "
                "or aliases like 'vendor_market_place'). If omitted, all fake seeders are run."
            ),
        )
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
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit businesses to seed (for business_payment_channels).",
        )
        parser.add_argument(
            "--business-id",
            type=int,
            action="append",
            dest="business_ids",
            default=None,
            help="Only seed these business ids (for business_payment_channels).",
        )
        parser.add_argument(
            "--no-config",
            action="store_true",
            help="Skip ensuring configuration / reference seeders have run.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all available fake / developing seeders and exit.",
        )

    def handle(self, *args, **options):
        if options.get("list"):
            self.stdout.write("Available developing / fake seeders:")
            for name in sorted(DEVELOPING_SEEDERS_MAP.keys()):
                cls_name = DEVELOPING_SEEDERS_MAP[name].__name__
                self.stdout.write(f"  - {name:<30} ({cls_name})")
            return

        target_name = options.get("seeder")
        if target_name:
            if target_name.lower() in ("list", "help"):
                self.stdout.write("Available developing / fake seeders:")
                for name in sorted(DEVELOPING_SEEDERS_MAP.keys()):
                    cls_name = DEVELOPING_SEEDERS_MAP[name].__name__
                    self.stdout.write(f"  - {name:<30} ({cls_name})")
                return

            seeder_cls = get_developing_seeder(target_name)
            if not seeder_cls:
                available = ", ".join(sorted(DEVELOPING_SEEDERS_MAP.keys()))
                raise CommandError(
                    f"Unknown developing seeder '{target_name}'.\n"
                    f"Available seeders: {available}"
                )

            self._run_single_seeder(seeder_cls, options)
        else:
            self._run_all_seeders(options)

    def _ensure_config(self):
        self.stdout.write("Ensuring configuration seeders have run...")
        for seeder_cls in CONFIG_SEEDERS:
            seeder_cls().run()

    def _run_single_seeder(self, seeder_cls, options):
        if not options.get("no_config"):
            self._ensure_config()

        if issubclass(seeder_cls, VendorMarketplaceSeeder):
            self.stdout.write(
                f"Running VendorMarketplaceSeeder ({options['vendors']} vendors, seed={options['seed']})..."
            )
            seeder = VendorMarketplaceSeeder(
                vendor_count=options["vendors"],
                seed=options["seed"],
            )
            counts = seeder.run()
            self.stdout.write(
                f"Vendor marketplace fixtures ready: "
                f"{counts.get('vendors_created', 0)} vendors, "
                f"{counts.get('businesses_created', 0)} businesses, "
                f"{counts.get('products_created', 0)} products, "
                f"{counts.get('variants_created', 0)} variants, "
                f"{counts.get('warehouses_created', 0)} warehouses, "
                f"{counts.get('supplies_created', 0)} supplies, "
                f"{counts.get('offers_created', 0)} offers."
            )
        elif issubclass(seeder_cls, CustomerSeeder):
            self.stdout.write("Running CustomerSeeder (fake customers)...")
            customer_seeder = CustomerSeeder()
            customer_seeder.run()
            self.stdout.write("Fake customers ready.")
        elif issubclass(seeder_cls, InventoryStockSeeder):
            self.stdout.write("Running InventoryStockSeeder...")
            stock_seeder = InventoryStockSeeder()
            stocked_count = stock_seeder.run()
            self.stdout.write(f"Stock adjusted for {stocked_count} variants.")
        elif issubclass(seeder_cls, BusinessPaymentChannelsSeeder):
            self.stdout.write("Running BusinessPaymentChannelsSeeder...")
            channel_seeder = BusinessPaymentChannelsSeeder(
                business_ids=options.get("business_ids"),
                limit=options.get("limit"),
            )
            created_channels = channel_seeder.run()
            self.stdout.write(f"Payment channels provisioned ({created_channels} created).")
        else:
            seeder = seeder_cls()
            seeder.run()

        self.stdout.write(
            self.style.SUCCESS(f"{seeder_cls.__name__} completed successfully.")
        )

    def _run_all_seeders(self, options):
        if not options.get("no_config"):
            self._ensure_config()

        self.stdout.write("Running CustomerSeeder (fake customers)...")
        customer_seeder = CustomerSeeder()
        customer_seeder.run()
        self.stdout.write("Fake customers ready.")

        self.stdout.write(
            f"Running VendorMarketplaceSeeder ({options['vendors']} vendors, seed={options['seed']})..."
        )
        marketplace_seeder = VendorMarketplaceSeeder(
            vendor_count=options["vendors"],
            seed=options["seed"],
        )
        counts = marketplace_seeder.run()
        self.stdout.write(
            f"Vendor marketplace fixtures ready: "
            f"{counts.get('vendors_created', 0)} vendors, "
            f"{counts.get('businesses_created', 0)} businesses, "
            f"{counts.get('products_created', 0)} products, "
            f"{counts.get('variants_created', 0)} variants, "
            f"{counts.get('warehouses_created', 0)} warehouses, "
            f"{counts.get('supplies_created', 0)} supplies, "
            f"{counts.get('offers_created', 0)} offers."
        )

        self.stdout.write("Running InventoryStockSeeder...")
        stock_seeder = InventoryStockSeeder()
        stocked_count = stock_seeder.run()
        self.stdout.write(f"Stock adjusted for {stocked_count} variants.")

        self.stdout.write("Running BusinessPaymentChannelsSeeder...")
        payment_channels_seeder = BusinessPaymentChannelsSeeder(
            business_ids=options.get("business_ids"),
            limit=options.get("limit"),
        )
        created_channels = payment_channels_seeder.run()
        self.stdout.write(f"Payment channels provisioned ({created_channels} created).")

        self.stdout.write(self.style.SUCCESS("All fake development seeders completed successfully."))
