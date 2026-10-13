from decimal import Decimal

from core.management.seeders.base import BaseSeeder
from domains.business.models import BusinessProfile
from domains.packages.data.features import FEATURE_SEED
from domains.packages.data.packages import PACKAGE_FEATURE_SEED, PACKAGE_SEED
from domains.packages.models import DEFAULT_PACKAGE_CODE, Feature, Package, PackageFeature


class PackagesSeeder(BaseSeeder):
    """Idempotent seed for packages, features, and their grants.

    Everything is keyed on ``code`` rather than ``id``, because ids are not
    portable between environments. Rows are created when absent and left
    untouched when present, so re-running never duplicates and never reverts
    an administrator's edits to a name, a price, or a feature config.
    Businesses left without a tier are converged onto ``free`` — the same
    default a profile gets at creation — so one ``seed`` run leaves the
    environment fully consistent.
    """

    def run(self):
        self._seed_features()
        self._seed_packages()
        self._seed_assignments()
        self._converge_null_assignments()

    @staticmethod
    def _seed_features():
        for record in FEATURE_SEED:
            Feature.objects.get_or_create(
                code=record["code"],
                defaults={
                    "name": record["name"],
                    "description": record["description"],
                },
            )

    @staticmethod
    def _seed_packages():
        for record in PACKAGE_SEED:
            Package.objects.get_or_create(
                code=record["code"],
                defaults={
                    "name": record["name"],
                    # Strings, not floats: money stays exact end to end, and
                    # the model's CheckConstraints are the real guard.
                    "price": Decimal(record["price"]),
                    "off_discount": Decimal(record["off_discount"]),
                    "is_active": record["is_active"],
                },
            )

    @staticmethod
    def _seed_assignments():
        for package_code, feature_code, config in PACKAGE_FEATURE_SEED:
            package = Package.objects.get(code=package_code)
            feature = Feature.objects.get(code=feature_code)
            # `defaults` applies only on insert, so an operator who retuned a
            # limit keeps their value on the next run.
            PackageFeature.objects.get_or_create(
                package=package,
                feature=feature,
                defaults={"config": config},
            )

    @staticmethod
    def _converge_null_assignments():
        """Put unassigned businesses on the default tier.

        A NULL `package` means "never assigned": migration 0010 backfilled
        the rows that existed then, so a leftover NULL is an environment
        that seeded late. The API treats NULL as `free` anyway — this makes
        the database say the same thing the gate already assumes.
        """
        free = Package.objects.filter(code=DEFAULT_PACKAGE_CODE).first()
        if free is None:
            return
        BusinessProfile.objects.filter(package__isnull=True).update(package=free)
