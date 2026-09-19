from rest_framework import serializers

from domains.catalog.api.serializers import ProductListSerializer, ProductDetailReadSerializer
from domains.catalog.models import Brand, Category, CategoryDetail, ProductDetails


class VendorProductSimilarSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    brand = serializers.DictField(allow_null=True)
    categories = serializers.ListField(child=serializers.DictField())
    status_name = serializers.CharField(allow_null=True)
    similarity = serializers.IntegerField()
    exact = serializers.BooleanField()
    thumbnail_url = serializers.URLField(allow_null=True)


class VendorProductCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=250)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
    )
    brand_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate_category_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each category can only be selected once.")
        existing = Category.objects.filter(id__in=value).count()
        if existing != len(value):
            raise serializers.ValidationError("One or more category IDs are invalid.")
        return value

    def validate_brand_id(self, value):
        if value is not None:
            if not Brand.objects.filter(pk=value).exists():
                raise serializers.ValidationError("Invalid brand ID.")
        return value

    def validate_details(self, value):
        for item in value:
            if "detail_id" not in item:
                raise serializers.ValidationError("Each detail must have a 'detail_id' field.")
        return value


class VendorProductUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=250, required=False)
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        required=False,
    )
    brand_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    json_description = serializers.JSONField(required=False, default=dict)
    details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate_category_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each category can only be selected once.")
        existing = Category.objects.filter(id__in=value).count()
        if existing != len(value):
            raise serializers.ValidationError("One or more category IDs are invalid.")
        return value

    def validate_brand_id(self, value):
        if value is not None:
            if not Brand.objects.filter(pk=value).exists():
                raise serializers.ValidationError("Invalid brand ID.")
        return value

    def validate_details(self, value):
        for item in value:
            if "detail_id" not in item:
                raise serializers.ValidationError("Each detail must have a 'detail_id' field.")
        return value


class VendorProductListSerializer(ProductListSerializer):
    editable = serializers.BooleanField(read_only=True)
    created_by_me = serializers.BooleanField(read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["editable", "created_by_me"]


class VendorProductDetailSerializer(ProductDetailReadSerializer):
    editable = serializers.BooleanField(read_only=True)
    created_by_me = serializers.BooleanField(read_only=True)

    class Meta(ProductDetailReadSerializer.Meta):
        fields = ProductDetailReadSerializer.Meta.fields + ["editable", "created_by_me"]
