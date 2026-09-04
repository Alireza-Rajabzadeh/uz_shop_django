from rest_framework import serializers
from domains.catalog.models import (
    Brand, Category, CategoryStatus, CategoryDetail,
    CategoryDetailRelation, Product, ProductStatus,
    ProductDetails, ProductFile, ProductVariantStatus, ProductVariants, VariantAttribute, VariantOption,
)
from domains.files.models import File
from domains.files.services import FileService
from domains.inventory.services import InventoryService


def primary_category(obj):
    return obj.categories.order_by("id").first()


class CategoryStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryStatus
        fields = "__all__"


class ProductVariantStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantStatus
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
        fields = ["id", "name", "fa_name", "slug", "parent", "parent_name", "status", "status_name", "logo"]


class CategoryNameSuggestionQuerySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    parent_id = serializers.IntegerField(required=False, min_value=1)
    exclude_id = serializers.IntegerField(required=False, min_value=1)


class CategoryNameSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    fa_name = serializers.CharField(allow_null=True)
    slug = serializers.CharField()
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


class BrandSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()

    @staticmethod
    def get_categories(brand):
        return [
            {"id": category.id, "name": category.name, "fa_name": category.fa_name}
            for category in brand.categories.all()
        ]

    class Meta:
        model = Brand
        fields = ["id", "name", "fa_name", "slug", "categories"]


class BrandWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    fa_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, allow_null=True
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), many=True, required=False
    )


class BrandNameSuggestionQuerySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    exclude_id = serializers.IntegerField(required=False, min_value=1)


class BrandNameSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    fa_name = serializers.CharField(allow_null=True)
    slug = serializers.CharField()
    similarity = serializers.IntegerField(read_only=True)
    exact = serializers.BooleanField(read_only=True)


class ProductListQuerySerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, min_value=1)
    name = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    category_id = serializers.IntegerField(required=False, min_value=1)
    brand_id = serializers.IntegerField(required=False, min_value=1)
    status_id = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    ordering = serializers.CharField(required=False, allow_blank=False)
    price_operator = serializers.ChoiceField(
        choices=["equal", "less_than", "greater_than", "between"], required=False
    )
    price = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=0, required=False
    )
    price_min = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=0, required=False
    )
    price_max = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=0, required=False
    )

    def validate(self, attrs):
        operator = attrs.get("price_operator")
        supplied = {key for key in ("price", "price_min", "price_max") if key in attrs}
        if not operator and supplied:
            raise serializers.ValidationError({"price_operator": "Select a price operator."})
        if not operator:
            return attrs
        expected = {"price_min", "price_max"} if operator == "between" else {"price"}
        if supplied != expected:
            raise serializers.ValidationError({
                "price": "Provide both range values for between, or one price for other operators."
            })
        if operator == "between" and attrs["price_min"] > attrs["price_max"]:
            raise serializers.ValidationError({"price_max": "Maximum price must not be below minimum price."})
        return attrs


class ProductDetailsSerializer(serializers.ModelSerializer):
    detail_name = serializers.CharField(source="detail.name", read_only=True)
    detail_type = serializers.CharField(source="detail.type", read_only=True)

    class Meta:
        model = ProductDetails
        fields = "__all__"


class VariantOptionSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)

    class Meta:
        model = VariantOption
        fields = ["id", "attribute", "attribute_name", "name", "fa_name", "info", "sku_code"]


class VariantAttributeSerializer(serializers.ModelSerializer):
    options = VariantOptionSerializer(many=True, read_only=True)

    class Meta:
        model = VariantAttribute
        fields = ["id", "name", "fa_name", "options"]


class VariantAttributeListSerializer(serializers.ModelSerializer):
    option_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = VariantAttribute
        fields = ["id", "name", "fa_name", "option_count"]


class VariantAttributeWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    fa_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True, allow_null=True
    )


class VariantOptionWriteSerializer(serializers.Serializer):
    attribute = serializers.PrimaryKeyRelatedField(queryset=VariantAttribute.objects.all())
    name = serializers.CharField(max_length=100)
    fa_name = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    info = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    sku_code = serializers.CharField(max_length=16)


class CategoryVariantAttributeAssignmentWriteSerializer(serializers.Serializer):
    attributes = serializers.PrimaryKeyRelatedField(
        queryset=VariantAttribute.objects.all(), many=True, allow_empty=True
    )

    def validate_attributes(self, attributes):
        ids = [attribute.id for attribute in attributes]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each variant attribute can only be assigned once.")
        return attributes


class ProductVariantSelectionSerializer(serializers.Serializer):
    attribute_id = serializers.IntegerField(source="attribute.id")
    attribute_name = serializers.CharField(source="attribute.name")
    option_id = serializers.IntegerField(source="option.id")
    option_name = serializers.CharField(source="option.name")
    option_fa_name = serializers.CharField(source="option.fa_name", allow_null=True)
    option_info = serializers.CharField(source="option.info", allow_null=True)
    sku_code = serializers.CharField(source="option.sku_code")


class ProductVariantSerializer(serializers.ModelSerializer):
    inventory_strategy_code = serializers.CharField(
        source="inventory_strategy.code", read_only=True
    )
    inventory_strategy_name = serializers.CharField(
        source="inventory_strategy.name", read_only=True
    )
    status_name = serializers.CharField(
        source="status.name", read_only=True, allow_null=True
    )
    selections = ProductVariantSelectionSerializer(many=True, read_only=True)
    total_item_count = serializers.SerializerMethodField()
    sellable_item_count = serializers.SerializerMethodField()
    available_item_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariants
        fields = [
            "id", "product", "sku", "price", "discount_type", "discount_value",
            "inventory_strategy", "inventory_strategy_code", "inventory_strategy_name",
            "status", "status_name",
            "selections", "total_item_count", "sellable_item_count",
            "available_item_count",
        ]
        read_only_fields = ["product", "sku", "inventory_strategy"]

    def _inventory_summary(self, obj):
        if hasattr(obj, "total_item_count"):
            return {
                "total_item_count": obj.total_item_count,
                "sellable_item_count": obj.sellable_item_count,
                "available_item_count": obj.available_item_count,
            }
        if not hasattr(obj, "_inventory_summary_cache"):
            obj._inventory_summary_cache = InventoryService().get_summary(obj)
        return obj._inventory_summary_cache

    def get_total_item_count(self, obj):
        return self._inventory_summary(obj)["total_item_count"]

    def get_sellable_item_count(self, obj):
        return self._inventory_summary(obj)["sellable_item_count"]

    def get_available_item_count(self, obj):
        return self._inventory_summary(obj)["available_item_count"]


class ProductSerializer(serializers.ModelSerializer):
    details = ProductDetailsSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    brand_fa_name = serializers.CharField(source="brand.fa_name", read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["status", "categories"]


class ProductFileReadSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    original_name = serializers.CharField(source="file.original_name", read_only=True)
    file_type = serializers.CharField(source="file.file_type", read_only=True)
    content_type = serializers.CharField(source="file.content_type", read_only=True)
    extension = serializers.CharField(source="file.extension", read_only=True)
    size = serializers.IntegerField(source="file.size", read_only=True)
    checksum = serializers.CharField(source="file.checksum", read_only=True)
    metadata = serializers.JSONField(source="file.metadata", read_only=True)

    class Meta:
        model = ProductFile
        fields = [
            "id", "file", "url", "original_name", "file_type", "content_type",
            "extension", "size", "checksum", "metadata", "role", "position",
            "is_primary", "alt_text", "created_at", "updated_at",
        ]

    def get_url(self, obj):
        try:
            return FileService().url(obj.file)
        except FileService.Error:
            return None


class ProductFileWriteSerializer(serializers.Serializer):
    file = serializers.PrimaryKeyRelatedField(
        queryset=File.objects.select_related("status")
    )
    role = serializers.ChoiceField(choices=ProductFile.Role.choices)
    position = serializers.IntegerField(min_value=0, default=0)
    is_primary = serializers.BooleanField(default=False)
    alt_text = serializers.CharField(max_length=255, allow_blank=True, default="")


class ProductFileUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ProductFile.Role.choices, required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    is_primary = serializers.BooleanField(required=False)
    alt_text = serializers.CharField(
        max_length=255, allow_blank=True, required=False
    )


class ProductFileReorderSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )


class ProductDetailReadSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    category_fa_name = serializers.SerializerMethodField()
    status_name = serializers.CharField(source="status.name", read_only=True)
    pictures = serializers.SerializerMethodField()
    details = ProductDetailsSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    brand_fa_name = serializers.CharField(source="brand.fa_name", read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "description", "json_description", "categories", "category_name", "category_fa_name",
            "status", "status_name", "brand", "brand_name", "brand_fa_name",
            "pictures", "details", "variants",
        ]

    def get_category_name(self, obj):
        category = primary_category(obj)
        return category.name if category else None

    def get_category_fa_name(self, obj):
        category = primary_category(obj)
        return category.fa_name if category else None

    def get_pictures(self, obj):
        relations = getattr(obj, "ordered_files", None)
        if relations is None:
            relations = obj.product_files.select_related(
                "file", "file__status"
            ).order_by("position", "id")
        return ProductFileReadSerializer(relations, many=True).data


class ProductBasicUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=250, required=False)
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    json_description = serializers.JSONField(required=False, default=dict)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(), required=False, allow_null=True
    )
    status = serializers.PrimaryKeyRelatedField(
        queryset=ProductStatus.objects.all(), required=False
    )


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    category_fa_name = serializers.SerializerMethodField()
    status_name = serializers.CharField(source="status.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    brand_fa_name = serializers.CharField(source="brand.fa_name", read_only=True, allow_null=True)
    variant_count = serializers.IntegerField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        category = primary_category(obj)
        return category.name if category else None

    def get_category_fa_name(self, obj):
        category = primary_category(obj)
        return category.fa_name if category else None

    def get_thumbnail_url(self, obj):
        media = getattr(obj, "list_media", [])
        if not media:
            return None
        try:
            return FileService().url(media[0].file)
        except FileService.Error:
            return None

    class Meta:
        model = Product
        fields = [
            "id", "name", "categories", "category_name", "category_fa_name", "brand",
            "brand_name", "brand_fa_name", "status", "status_name",
            "description", "json_description", "variant_count", "thumbnail_url",
        ]


class ProductCategorySelectionSerializer(serializers.Serializer):
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        allow_empty=False,
    )


class ProductDetailValueWriteSerializer(serializers.Serializer):
    detail_id = serializers.PrimaryKeyRelatedField(
        queryset=CategoryDetail.objects.all(),
        source="detail",
    )
    value = serializers.CharField(max_length=250, allow_blank=True)


class ProductVariantSelectionWriteSerializer(serializers.Serializer):
    attribute_id = serializers.PrimaryKeyRelatedField(
        queryset=VariantAttribute.objects.all(), source="attribute"
    )
    option_id = serializers.PrimaryKeyRelatedField(
        queryset=VariantOption.objects.select_related("attribute"), source="option"
    )


class NormalInventoryWriteSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0)
    sellable = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if attrs["sellable"] > attrs["quantity"]:
            raise serializers.ValidationError("Sellable quantity cannot exceed physical quantity.")
        return attrs


class SerializedItemWriteSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, required=False)
    serial_number = serializers.CharField(max_length=100, trim_whitespace=True)
    on_sale = serializers.BooleanField()


class ProductVariantWriteSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0, required=False, default="0")
    discount_type = serializers.ChoiceField(
        choices=["percentage", "fixed"], required=False, allow_null=True
    )
    discount_value = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    status_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariantStatus.objects.all(),
        source="status",
        required=False,
        allow_null=True,
    )
    selections = ProductVariantSelectionWriteSerializer(many=True, required=False)
    inventory_strategy_code = serializers.ChoiceField(
        choices=["normal", "serialized"], required=False
    )
    inventory = NormalInventoryWriteSerializer(required=False)
    serial_items = SerializedItemWriteSerializer(many=True, required=False)

    def validate(self, attrs):
        if "sku" in self.initial_data:
            raise serializers.ValidationError({"sku": "SKU is generated by the backend."})
        current_code = (
            self.instance.inventory_strategy.code if self.instance is not None else None
        )
        strategy_code = attrs.get("inventory_strategy_code", current_code)
        if strategy_code is None:
            strategy_code = "normal"
            attrs["inventory_strategy_code"] = strategy_code
        strategy_changed = current_code is not None and strategy_code != current_code
        if strategy_changed:
            required_field = "inventory" if strategy_code == "normal" else "serial_items"
            if required_field not in self.initial_data:
                raise serializers.ValidationError({
                    required_field: f"This field is required for {strategy_code} inventory."
                })
        if "inventory" in self.initial_data and strategy_code != "normal":
            raise serializers.ValidationError({
                "inventory": "Inventory quantity is only valid for normal strategy."
            })
        if "serial_items" in self.initial_data and strategy_code != "serialized":
            raise serializers.ValidationError({
                "serial_items": "Serial items are only valid for serialized strategy."
            })
        attrs["inventory_submitted"] = (
            "inventory" in self.initial_data or "serial_items" in self.initial_data
        )
        return self._validate_pricing(attrs)

    def validate_selections(self, selections):
        ids = [item["attribute"].id for item in selections]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each attribute can only be selected once.")
        return selections

    def _validate_pricing(self, attrs):
        discount_type = attrs.get(
            "discount_type", getattr(self.instance, "discount_type", None)
        )
        discount_value = attrs.get(
            "discount_value", getattr(self.instance, "discount_value", None)
        )
        price = attrs.get("price", getattr(self.instance, "price", None))
        if bool(discount_type) != (discount_value is not None):
            raise serializers.ValidationError({
                "discount_value": "Discount type and value must be provided together."
            })
        if discount_type == "percentage" and discount_value > 100:
            raise serializers.ValidationError({
                "discount_value": "Percentage discount cannot exceed 100."
            })
        if discount_type == "fixed" and price is not None and discount_value > price:
            raise serializers.ValidationError({
                "discount_value": "Fixed discount cannot exceed the price."
            })
        return attrs


class ProductCompleteCreateSerializer(ProductCategorySelectionSerializer):
    name = serializers.CharField(max_length=250)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    json_description = serializers.JSONField(required=False, default=dict)
    brand = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(), required=False, allow_null=True
    )
    details = ProductDetailValueWriteSerializer(many=True, required=False, default=list)

    def validate_details(self, details):
        ids = [item["detail"].id for item in details]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product detail can only be submitted once.")
        return details
