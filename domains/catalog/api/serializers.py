from rest_framework import serializers
from domains.catalog.models import (
    Category, CategoryStatus, CategoryDetail,
    CategoryDetailRelation, Product, ProductStatus,
    ProductDetails, ProductVariants, ProductVariantsDetails,
)


class CategoryStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryStatus
        fields = "__all__"


class CategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryDetail
        fields = "__all__"


class CategoryDetailRelationSerializer(serializers.ModelSerializer):
    detail_name = serializers.CharField(source="detail.name", read_only=True)
    detail_type = serializers.CharField(source="detail.type", read_only=True)

    class Meta:
        model = CategoryDetailRelation
        fields = "__all__"


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = "__all__"

    def get_children(self, obj):
        children = obj.children.all()
        if children:
            return CategorySerializer(children, many=True).data
        return []


class CategoryListSerializer(serializers.ModelSerializer):
    status_name = serializers.CharField(source="status.name", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)

    class Meta:
        model = Category
        fields = ["id", "name", "parent", "parent_name", "status", "status_name", "logo"]


class ProductStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductStatus
        fields = "__all__"


class ProductDetailsSerializer(serializers.ModelSerializer):
    detail_name = serializers.CharField(source="detail.name", read_only=True)
    detail_type = serializers.CharField(source="detail.type", read_only=True)

    class Meta:
        model = ProductDetails
        fields = "__all__"


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariants
        fields = "__all__"


class ProductVariantDetailsSerializer(serializers.ModelSerializer):
    detail_name = serializers.CharField(source="detail.name", read_only=True)

    class Meta:
        model = ProductVariantsDetails
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):
    details = ProductDetailsSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = "__all__"


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_name = serializers.CharField(source="status.name", read_only=True)
    variant_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "category", "category_name", "status", "status_name", "description", "variant_count"]

    def get_variant_count(self, obj):
        return obj.products.count()
