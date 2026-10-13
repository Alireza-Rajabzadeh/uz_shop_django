from decimal import Decimal

from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import Feature, Package, PackageFeature, PackagePriceHistory

# Structural rules every config must satisfy, keyed by feature code. A new
# feature that needs bespoke validation adds one entry here instead of
# another branch in `validate_feature_config`.
FEATURE_CONFIG_RULES = {}

# Keys whose types are fixed for every feature. Unknown keys pass through
# untouched, so a feature can carry its own settings without a schema change.
CONFIG_BOOLEAN_KEYS = ("enabled",)
CONFIG_INTEGER_KEYS = ("limit",)


def validate_feature_config(value, *, feature_code=None):
    """Validate one feature configuration document.

    Deliberately structural only. No feature declares a maximum here, so
    limits are checked for shape and sign but never for being small enough;
    that is a product decision, not a validation-layer one.
    """
    if not isinstance(value, dict):
        raise serializers.ValidationError(
            _("Feature configuration must be a JSON object.")
        )

    errors = {}

    for key in CONFIG_BOOLEAN_KEYS:
        if key in value and not isinstance(value[key], bool):
            errors[key] = _("This setting must be a boolean.")

    for key in CONFIG_INTEGER_KEYS:
        if key not in value:
            continue
        limit = value[key]
        # `bool` subclasses `int` in Python, so `True` would otherwise pass
        # the non-negative integer check below.
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            errors[key] = _("This setting must be a non-negative integer.")

    if errors:
        raise serializers.ValidationError(errors)

    rule = FEATURE_CONFIG_RULES.get(feature_code)
    if rule is not None:
        rule(value)

    return value


def _validate_config_for(attrs, instance=None):
    """Resolve the owning feature, then validate `attrs["config"]` against it.

    Runs from `Serializer.validate`, where every field of the request is
    already resolved, because a field-level `validate_config` cannot see the
    `feature` that arrived in the same payload.
    """
    feature = attrs.get("feature") or getattr(instance, "feature", None)
    attrs["config"] = validate_feature_config(
        attrs.get("config") or {},
        feature_code=feature.code if feature else None,
    )
    return attrs


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "code", "name", "description", "created_at", "updated_at"]
        read_only_fields = fields


class FeatureCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["id", "code", "name", "description"]
        read_only_fields = ["id"]


class FeatureUpdateSerializer(serializers.ModelSerializer):
    # `code` is deliberately absent: it is the stable identifier other code
    # keys off, so it is created once and never edited.
    class Meta:
        model = Feature
        fields = ["name", "description"]


class PackageFeatureSerializer(serializers.ModelSerializer):
    feature = FeatureSerializer(read_only=True)

    class Meta:
        model = PackageFeature
        fields = ["id", "feature", "config", "created_at", "updated_at"]
        read_only_fields = fields


class PackageFeatureAssignSerializer(serializers.ModelSerializer):
    feature = serializers.PrimaryKeyRelatedField(queryset=Feature.objects.all())
    config = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = PackageFeature
        fields = ["id", "feature", "config"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        return _validate_config_for(attrs, self.instance)


class PackageFeatureConfigSerializer(serializers.ModelSerializer):
    config = serializers.JSONField()

    class Meta:
        model = PackageFeature
        fields = ["config"]

    def validate(self, attrs):
        return _validate_config_for(attrs, self.instance)


class PackageSerializer(serializers.ModelSerializer):
    features = PackageFeatureSerializer(source="package_features", many=True)

    class Meta:
        model = Package
        fields = [
            "id",
            "code",
            "name",
            "price",
            "off_discount",
            "is_active",
            "features",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PackageCreateSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0"),
        error_messages={"min_value": _("Price cannot be negative.")},
    )
    off_discount = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        error_messages={
            "min_value": _("Discount cannot be negative."),
            "max_value": _("Discount must be a percentage between 0 and 100."),
        },
    )

    class Meta:
        model = Package
        fields = ["id", "code", "name", "price", "off_discount", "is_active"]
        read_only_fields = ["id"]


class PackageUpdateSerializer(serializers.ModelSerializer):
    # `code` is deliberately absent; it is created once and never edited.
    price = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0"),
        error_messages={"min_value": _("Price cannot be negative.")},
    )
    off_discount = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        error_messages={
            "min_value": _("Discount cannot be negative."),
            "max_value": _("Discount must be a percentage between 0 and 100."),
        },
    )

    class Meta:
        model = Package
        fields = ["name", "price", "off_discount", "is_active"]


class PackagePriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PackagePriceHistory
        fields = ["id", "price", "off_discount", "created_at"]
        read_only_fields = fields
