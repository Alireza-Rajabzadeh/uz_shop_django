from rest_framework import serializers


class DigikalaListingCreateSerializer(serializers.Serializer):
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=5,
    )
    products_per_category = serializers.IntegerField(min_value=1, max_value=20)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=60, default=30)
    retries = serializers.IntegerField(min_value=1, max_value=5, default=3)
    delay_seconds = serializers.FloatField(min_value=0.5, max_value=10, default=1.0)
    include_ads = serializers.BooleanField(default=False)

    def validate_category_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Category IDs must be unique.")
        return value


class DigikalaSelectionSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["all", "ids"])
    product_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        max_length=100,
    )

    def validate(self, attrs):
        ids = attrs.get("product_ids", [])
        if attrs["mode"] == "ids" and not ids:
            raise serializers.ValidationError(
                {"product_ids": "Select at least one product."}
            )
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                {"product_ids": "Product IDs must be unique."}
            )
        if attrs["mode"] == "all":
            attrs.pop("product_ids", None)
        return attrs


class DigikalaImportOptionsSerializer(serializers.Serializer):
    update_existing = serializers.BooleanField(default=True)
    download_media = serializers.BooleanField(default=False)
    dry_run = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs["update_existing"]:
            raise serializers.ValidationError(
                {"update_existing": "The pilot requires safe source refresh."}
            )
        if attrs["dry_run"]:
            raise serializers.ValidationError(
                {"dry_run": "Dry-run import is not implemented yet."}
            )
        return attrs


class DigikalaImportCreateSerializer(serializers.Serializer):
    listing_id = serializers.UUIDField()
    listing_sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")
    selection = DigikalaSelectionSerializer()
    options = DigikalaImportOptionsSerializer()
