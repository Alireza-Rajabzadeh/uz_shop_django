from rest_framework import serializers

from domains.catalog.api.serializers import (
    ProductDetailsSerializer,
    ProductFileReadSerializer,
    primary_category,
)
from domains.catalog.models import (
    Brand,
    Category,
    VendorProduct,
    VendorProductDetails,
    VendorProductFile,
)
from domains.catalog.services.vendor_product_submission_service import (
    vendor_product_submission_service,
)


class VendorSubmissionFileSerializer(ProductFileReadSerializer):
    class Meta(ProductFileReadSerializer.Meta):
        model = VendorProductFile


class VendorSubmissionDetailsSerializer(ProductDetailsSerializer):
    class Meta(ProductDetailsSerializer.Meta):
        model = VendorProductDetails


class VendorSubmissionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "fa_name", "slug"]


class VendorProductSubmissionListSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source="status.name", read_only=True)
    brand_name = serializers.CharField(
        source="brand.name", read_only=True, allow_null=True
    )
    brand_fa_name = serializers.CharField(
        source="brand.fa_name", read_only=True, allow_null=True
    )
    category_name = serializers.SerializerMethodField()
    category_fa_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()
    changed_fields = serializers.SerializerMethodField()

    class Meta:
        model = VendorProduct
        fields = [
            "id", "name", "status", "status_name", "product",
            "categories", "category_name", "category_fa_name",
            "brand", "brand_name", "brand_fa_name",
            "description", "admin_response",
            "confirmed_at", "created_at", "updated_at",
            "thumbnail_url", "editable", "changed_fields",
        ]

    def get_category_name(self, obj):
        category = primary_category(obj)
        return category.name if category else None

    def get_category_fa_name(self, obj):
        category = primary_category(obj)
        return category.fa_name if category else None

    def get_thumbnail_url(self, obj):
        media = obj.product_files.select_related("file", "file__status").order_by(
            "position", "id"
        ).first()
        if media is None:
            return None
        from domains.files.services import FileService
        try:
            return FileService().url(media.file)
        except FileService.Error:
            return None

    def get_editable(self, obj):
        return vendor_product_submission_service.is_editable(obj)

    def get_changed_fields(self, obj):
        # A first-time draft has no live counterpart yet; every field is new.
        if not obj.product_id:
            return sorted(vendor_product_submission_service.APPLYABLE_FIELDS)
        return sorted(vendor_product_submission_service.changed_fields(obj))


class VendorProductSubmissionDetailSerializer(VendorProductSubmissionListSerializer):
    details = serializers.SerializerMethodField()
    pictures = serializers.SerializerMethodField()

    class Meta(VendorProductSubmissionListSerializer.Meta):
        fields = VendorProductSubmissionListSerializer.Meta.fields + [
            "json_description", "details", "pictures",
        ]

    def get_details(self, obj):
        rows = obj.details.select_related("detail").order_by("detail_id")
        return VendorSubmissionDetailsSerializer(rows, many=True).data

    def get_pictures(self, obj):
        rows = obj.product_files.select_related("file", "file__status").order_by(
            "position", "id"
        )
        return VendorSubmissionFileSerializer(rows, many=True).data


class VendorProductSubmissionCreateSerializer(serializers.Serializer):
    """Two mutually exclusive lanes in one endpoint.

    `product_id` opens the revision draft for an existing catalog product;
    anything else opens a first-time draft.
    """

    product_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=250, required=False)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )
    brand_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    json_description = serializers.JSONField(required=False, default=dict)
    details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        if attrs.get("product_id") is not None:
            extras = [
                field
                for field in ("name", "category_ids", "brand_id", "description",
                              "json_description", "details")
                if field in attrs and attrs[field] not in (None, [], {}, "")
            ]
            if extras:
                raise serializers.ValidationError(
                    "Send either 'product_id' or the product fields, not both."
                )
            return {"product_id": attrs["product_id"]}

        missing = [field for field in ("name", "category_ids") if not attrs.get(field)]
        if missing:
            raise serializers.ValidationError(
                {field: "This field is required." for field in missing}
            )
        return attrs

    def validate_category_ids(self, value):
        return _validate_category_ids(value)

    def validate_brand_id(self, value):
        return _validate_brand_id(value)


class VendorProductSubmissionUpdateSerializer(serializers.Serializer):
    """Partial by design: only the keys sent are staged, the rest keep their
    current submission value."""

    name = serializers.CharField(max_length=250, required=False)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
    )
    brand_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    json_description = serializers.JSONField(required=False)
    details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
    )

    def validate_category_ids(self, value):
        return _validate_category_ids(value)

    def validate_brand_id(self, value):
        return _validate_brand_id(value)


def _validate_category_ids(value):
    if len(value) != len(set(value)):
        raise serializers.ValidationError(
            "Each category can only be selected once."
        )
    existing = Category.objects.filter(id__in=value).count()
    if existing != len(value):
        raise serializers.ValidationError("One or more category IDs are invalid.")
    return value


def _validate_brand_id(value):
    if value is not None and not Brand.objects.filter(pk=value).exists():
        raise serializers.ValidationError("Invalid brand ID.")
    return value
