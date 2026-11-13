from decimal import Decimal

from core.management.seeders.base import BaseSeeder
from domains.business.models import BusinessProfile
from domains.packages.data.features import FEATURE_SEED
from domains.packages.data.packages import PACKAGE_FEATURE_SEED, PACKAGE_SEED
from domains.packages.enums import PackageCodeEnum, PackageFeatureEnum
from domains.packages.models import DEFAULT_PACKAGE_CODE, Feature, Package, PackageFeature


class PackagesSeeder(BaseSeeder):
    """Idempotent seed for packages, features, and their grants using Enums."""

    def run(self):
        self._seed_features()
        self._seed_packages()
        self._seed_assignments()
        self._converge_null_assignments()
        self.sync_sequences(Feature, Package, PackageFeature)

    @staticmethod
    def _seed_features():
        feature_map = {f.code: f for f in PackageFeatureEnum}
        for record in FEATURE_SEED:
            f_enum = feature_map.get(record["code"])
            defaults = {
                "name": record["name"],
                "description": record["description"],
            }
            if f_enum:
                Feature.objects.update_or_create(
                    id=f_enum.value,
                    defaults={"code": record["code"], **defaults},
                )
            else:
                Feature.objects.update_or_create(
                    code=record["code"],
                    defaults=defaults,
                )

    @staticmethod
    def _seed_packages():
        package_map = {p.code: p for p in PackageCodeEnum}
        for record in PACKAGE_SEED:
            p_enum = package_map.get(record["code"])
            defaults = {
                "name": record["name"],
                "price": Decimal(record["price"]),
                "off_discount": Decimal(record["off_discount"]),
                "is_active": record["is_active"],
            }
            if p_enum:
                Package.objects.update_or_create(
                    id=p_enum.value,
                    defaults={"code": record["code"], **defaults},
                )
            else:
                Package.objects.update_or_create(
                    code=record["code"],
                    defaults=defaults,
                )

    @staticmethod
    def _seed_assignments():
        for package_code, feature_code, config in PACKAGE_FEATURE_SEED:
            package = Package.objects.filter(code=package_code).first()
            feature = Feature.objects.filter(code=feature_code).first()
            if package is None or feature is None:
                continue
            PackageFeature.objects.get_or_create(
                package=package,
                feature=feature,
                defaults={"config": config},
            )

    @staticmethod
    def _converge_null_assignments():
        default_package = Package.objects.filter(
            code=DEFAULT_PACKAGE_CODE or PackageCodeEnum.FREE.code
        ).first()
        if default_package is None:
            return
        BusinessProfile.objects.filter(package__isnull=True).update(package=default_package)
