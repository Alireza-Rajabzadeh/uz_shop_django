from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from core.management.seeders.packages import PackagesSeeder
from domains.packages.data.features import FEATURE_SEED
from domains.packages.data.packages import PACKAGE_FEATURE_SEED, PACKAGE_SEED
from domains.packages.models import Feature, Package, PackageFeature, PackagePriceHistory
from domains.packages.serializers import validate_feature_config


def seed_twice():
    PackagesSeeder().run()
    PackagesSeeder().run()


def counts():
    return (
        Package.objects.count(),
        Feature.objects.count(),
        PackageFeature.objects.count(),
        PackagePriceHistory.objects.count(),
    )


class PackagesSeederTests(TestCase):
    """Idempotency and safety of `PackagesSeeder` itself.

    These drive the seeder directly rather than through `manage.py seed`,
    because the command runs all nineteen seeders and costs about 97s per
    call. The wiring into `manage.py seed` is asserted once, in
    `test_seed_command_runs_packages_seeder`.
    """

    def test_seed_creates_every_feature_package_and_assignment(self):
        PackagesSeeder().run()

        self.assertEqual(Feature.objects.count(), len(FEATURE_SEED))
        self.assertEqual(Package.objects.count(), len(PACKAGE_SEED))
        self.assertEqual(PackageFeature.objects.count(), len(PACKAGE_FEATURE_SEED))

    def test_seeding_twice_creates_no_duplicates(self):
        seed_twice()

        self.assertEqual(Feature.objects.count(), len(FEATURE_SEED))
        self.assertEqual(Package.objects.count(), len(PACKAGE_SEED))
        self.assertEqual(PackageFeature.objects.count(), len(PACKAGE_FEATURE_SEED))

    def test_seeding_twice_adds_no_extra_price_history(self):
        seed_twice()

        # One row per package from the initial create, and nothing from the
        # second run.
        self.assertEqual(
            PackagePriceHistory.objects.count(), len(PACKAGE_SEED)
        )

    def test_seed_run_is_a_noop_on_an_already_seeded_database(self):
        PackagesSeeder().run()
        before = counts()

        PackagesSeeder().run()

        self.assertEqual(counts(), before)

    def test_seeding_creates_initial_price_history(self):
        PackagesSeeder().run()

        for record in PACKAGE_SEED:
            package = Package.objects.get(code=record["code"])
            history = list(package.price_history.all())
            self.assertEqual(len(history), 1, msg=record["code"])
            self.assertEqual(history[0].price, Decimal(record["price"]))
            self.assertEqual(history[0].off_discount, Decimal(record["off_discount"]))

    def test_seeding_after_a_price_change_adds_no_extra_history(self):
        PackagesSeeder().run()
        plus = Package.objects.get(code="plus")
        plus.price = Decimal("750000.00")
        plus.save()

        PackagesSeeder().run()

        history = list(plus.price_history.all())
        # The seeded row plus the one from the repricing, and nothing from
        # the second seed run.
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1].price, Decimal("750000.00"))

    def test_second_run_does_not_revert_an_admin_edited_price(self):
        PackagesSeeder().run()
        pro = Package.objects.get(code="pro")
        pro.price = Decimal("999.00")
        pro.save()

        PackagesSeeder().run()

        self.assertEqual(Package.objects.get(code="pro").price, Decimal("999.00"))

    def test_second_run_does_not_revert_edited_names(self):
        PackagesSeeder().run()
        Package.objects.filter(code="free").update(name="Starter")
        Feature.objects.filter(code="shop.api").update(name="Integrations")

        PackagesSeeder().run()

        self.assertEqual(Package.objects.get(code="free").name, "Starter")
        self.assertEqual(Feature.objects.get(code="shop.api").name, "Integrations")

    def test_second_run_does_not_revert_an_edited_feature_config(self):
        PackagesSeeder().run()
        package = Package.objects.get(code="free")
        feature = Feature.objects.get(code="shop.products")
        PackageFeature.objects.filter(package=package, feature=feature).update(
            config={"enabled": True, "limit": 12}
        )

        PackagesSeeder().run()

        assignment = PackageFeature.objects.get(package=package, feature=feature)
        self.assertEqual(assignment.config, {"enabled": True, "limit": 12})

    def test_assignments_resolve_by_code_not_by_id(self):
        PackagesSeeder().run()

        for package_code, feature_code, _config in PACKAGE_FEATURE_SEED:
            package = Package.objects.get(code=package_code)
            feature = Feature.objects.get(code=feature_code)
            self.assertTrue(
                PackageFeature.objects.filter(package=package, feature=feature).exists(),
                msg=f"{package_code}/{feature_code}",
            )

    def test_seeded_configs_pass_domain_validation(self):
        # The seeder writes configs straight to the model, so assert here
        # that what it writes is what the API would have accepted.
        PackagesSeeder().run()

        for _package_code, feature_code, config in PACKAGE_FEATURE_SEED:
            validate_feature_config(config, feature_code=feature_code)

    def test_seeded_feature_codes_match_the_documented_contract(self):
        PackagesSeeder().run()

        self.assertEqual(
            sorted(Feature.objects.values_list("code", flat=True)),
            sorted(record["code"] for record in FEATURE_SEED),
        )
        self.assertEqual(
            sorted(Package.objects.values_list("code", flat=True)),
            sorted(record["code"] for record in PACKAGE_SEED),
        )

    def test_seed_command_runs_packages_seeder(self):
        # One full `manage.py seed` (~97s: it runs all nineteen seeders) to
        # prove the wiring, not to re-test idempotency above.
        call_command("seed")

        self.assertEqual(Package.objects.count(), len(PACKAGE_SEED))
        self.assertEqual(Feature.objects.count(), len(FEATURE_SEED))
        self.assertEqual(PackageFeature.objects.count(), len(PACKAGE_FEATURE_SEED))
