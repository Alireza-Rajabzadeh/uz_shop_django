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


class CategoryDetailNameSuggestionQuerySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    exclude_id = serializers.IntegerField(required=False, min_value=1)


class CategoryDetailNameSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    type = serializers.CharField()
    required = serializers.BooleanField()
    options = serializers.CharField(allow_blank=True)
    filterable = serializers.BooleanField()
    similarity = serializers.IntegerField()
    exact = serializers.BooleanField()


class CategoryDetailAssignmentWriteSerializer(serializers.Serializer):
    details = serializers.PrimaryKeyRelatedField(
        queryset=CategoryDetail.objects.all(),
        many=True,
        allow_empty=True,
    )

    def validate_details(self, details):
        ids = [detail.id for detail in details]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each category detail can only be assigned once.")
        return details


class CategoryDetailAssignmentOptionSerializer(CategoryDetailSerializer):
    assigned = serializers.SerializerMethodField()
    in_use = serializers.SerializerMethodField()

    class Meta(CategoryDetailSerializer.Meta):
        fields = [
            "id", "name", "type", "required", "options", "filterable",
            "assigned", "in_use",
        ]

    def get_assigned(self, obj):
        return obj.id in self.context.get("assigned_ids", set())

    def get_in_use(self, obj):
        return obj.id in self.context.get("used_ids", set())


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


class CategoryNameSuggestionQuerySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    exclude_id = serializers.IntegerField(required=False, min_value=1)


class CategoryNameSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    parent = serializers.IntegerField(allow_null=True)
    parent_name = serializers.CharField(allow_null=True)
    status = serializers.IntegerField()
    status_name = serializers.CharField()
    logo = serializers.CharField(allow_null=True)
    similarity = serializers.IntegerField(read_only=True)
    exact = serializers.BooleanField(read_only=True)


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
    variant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "category", "category_name", "status", "status_name", "description", "variant_count"]


class ProductCategorySelectionSerializer(serializers.Serializer):
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        allow_empty=False,
    )

    def validate_category_ids(self, categories):
        if len(categories) != 1:
            raise serializers.ValidationError(
                "Exactly one category is supported until product categories become many-to-many."
            )
        return categories


class ProductDetailValueWriteSerializer(serializers.Serializer):
    detail_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryDetail.objects.all(),
        source="detail",
    )
    value = serializers.CharField(max_length=250, allow_blank=True)


class ProductCompleteCreateSerializer(ProductCategorySelectionSerializer):
    name = serializers.CharField(max_length=250)
    status = serializers.PrimaryKeyRelatedField(queryset=ProductStatus.objects.all())
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    details = ProductDetailValueWriteSerializer(many=True, required=False, default=list)

    def validate_details(self, details):
        ids = [item["detail"].id for item in details]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product detail can only be submitted once.")
        return details
