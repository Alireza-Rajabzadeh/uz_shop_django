from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from .models import DEFAULT_PACKAGE_CODE, Feature, Package, PackageFeature


class PackageService:
    """Reads and multi-step writes for the packages domain.

    Views resolve HTTP concerns and call in here; the service owns the
    queries and the transactions that must commit together. The service
    deliberately does not write `PackagePriceHistory`: that is handled once,
    at the model layer by `domains.packages.signals`, so no caller can
    record pricing without leaving an audit row.
    """

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    # --- packages -----------------------------------------------------

    @staticmethod
    def list_packages():
        # Prefetched so serializing a page of packages and their features
        # stays at two queries instead of one per package.
        return Package.objects.prefetch_related("package_features__feature")

    @staticmethod
    def get_package(package_id):
        try:
            return Package.objects.prefetch_related("package_features__feature").get(
                id=package_id
            )
        except Package.DoesNotExist as exc:
            raise PackageService.ValidationError(
                {"package_id": [_("Package not found.")]}
            ) from exc

    @classmethod
    @transaction.atomic
    def create_package(cls, **values):
        return Package.objects.create(**values)

    @classmethod
    @transaction.atomic
    def update_package(cls, package, **values):
        for field, value in values.items():
            setattr(package, field, value)
        # A single save, so a price and discount edited together produce one
        # history row rather than two.
        package.save()
        return package

    @staticmethod
    def price_history(package):
        return package.price_history.all()

    # --- entitlement --------------------------------------------------

    @staticmethod
    def resolve_package(business):
        """The package a business is on.

        Both a NULL relation and a vendor with no business profile yet read
        as the default tier, which is the same rule `BusinessProfile.
        package_code` encodes; neither state is an error.
        """
        if business is not None and business.package_id:
            return business.package
        return Package.objects.filter(code=DEFAULT_PACKAGE_CODE).first()

    @staticmethod
    def features_for(package):
        """Feature codes ``package`` makes available right now.

        Availability is decided here so no caller — panel, proxy, or view —
        has to know the rules: a missing package, an inactive tier, or a
        disabled grant simply does not appear in the result.
        """
        if package is None or not package.is_active:
            return []
        return [
            grant.feature.code
            for grant in package.package_features.select_related("feature")
            if grant.config.get("enabled", True)
        ]

    @classmethod
    def available_features(cls, business):
        return cls.features_for(cls.resolve_package(business))

    # --- features -----------------------------------------------------

    @staticmethod
    def list_features():
        return Feature.objects.all()

    @staticmethod
    def get_feature(feature_id):
        try:
            return Feature.objects.get(id=feature_id)
        except Feature.DoesNotExist as exc:
            raise PackageService.ValidationError(
                {"feature_id": [_("Feature not found.")]}
            ) from exc

    @classmethod
    @transaction.atomic
    def create_feature(cls, **values):
        return Feature.objects.create(**values)

    @classmethod
    @transaction.atomic
    def update_feature(cls, feature, **values):
        for field, value in values.items():
            setattr(feature, field, value)
        feature.save()
        return feature

    # --- package features --------------------------------------------

    @staticmethod
    def list_package_features(package):
        return package.package_features.select_related("feature")

    @classmethod
    @transaction.atomic
    def assign_feature(cls, package, feature, config):
        try:
            return PackageFeature.objects.create(
                package=package, feature=feature, config=config
            )
        except IntegrityError as exc:
            # The unique constraint on (package, feature) is the real guard
            # against a duplicate; translate it into the project's error
            # shape rather than letting it surface as a 500.
            raise cls.ValidationError(
                {"feature_id": [_("This feature is already assigned to the package.")]}
            ) from exc

    @staticmethod
    def get_package_feature(package, feature_id):
        try:
            return package.package_features.select_related("feature").get(
                feature_id=feature_id
            )
        except PackageFeature.DoesNotExist as exc:
            raise PackageService.ValidationError(
                {"feature_id": [_("This feature is not assigned to the package.")]}
            ) from exc

    @classmethod
    @transaction.atomic
    def update_feature_config(cls, package_feature, config):
        package_feature.config = config
        package_feature.save()
        return package_feature

    @classmethod
    @transaction.atomic
    def remove_feature(cls, package_feature):
        package_feature.delete()
