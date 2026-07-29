from rest_framework import serializers

from domains.inventory.models import Warehouse


class ClosedSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["This field is not allowed."] for key in unknown})
        return super().to_internal_value(data)


class WarehouseContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()


class InventoryStrategySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class SelectionSerializer(serializers.Serializer):
    attribute_id = serializers.IntegerField()
    attribute_name = serializers.CharField()
    option_id = serializers.IntegerField()
    option_name = serializers.CharField()


class NamedObjectSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class NormalInventoryDetailSerializer(serializers.Serializer):
    warehouse = WarehouseContextSerializer()
    quantity = serializers.IntegerField()
    sellable = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()
    min_stock = serializers.IntegerField()


class NormalInventoryWriteSerializer(ClosedSerializer):
    quantity = serializers.IntegerField(min_value=0)
    sellable = serializers.IntegerField(min_value=0)
    min_stock = serializers.IntegerField(min_value=0)


class SerializedStatusSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class SerializedItemDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    serial_number = serializers.CharField()
    on_sale = serializers.BooleanField()
    reserved = serializers.BooleanField()
    status = SerializedStatusSerializer()
    warehouse = WarehouseContextSerializer()
    editable = serializers.BooleanField()


class SerializedItemWriteSerializer(ClosedSerializer):
    id = serializers.IntegerField(min_value=1, required=False)
    serial_number = serializers.CharField(max_length=100, trim_whitespace=False)
    on_sale = serializers.BooleanField()


class VariantStockWriteSerializer(ClosedSerializer):
    inventory = NormalInventoryWriteSerializer(required=False)
    serial_items = SerializedItemWriteSerializer(many=True, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if set(attrs) != {"inventory"} and set(attrs) != {"serial_items"}:
            raise serializers.ValidationError("Submit exactly one editable inventory snapshot.")
        return attrs


class VariantInventoryDetailSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    sku = serializers.CharField()
    product = NamedObjectSerializer()
    category = NamedObjectSerializer()
    selections = SelectionSerializer(many=True)
    strategy = InventoryStrategySerializer()
    total_item_count = serializers.IntegerField()
    sellable_item_count = serializers.IntegerField()
    available_item_count = serializers.IntegerField()
    inventory = NormalInventoryDetailSerializer(allow_null=True)
    serial_items = SerializedItemDetailSerializer(many=True, allow_null=True)


class InventoryVariantQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    product = serializers.IntegerField(min_value=1, required=False)
    category = serializers.IntegerField(min_value=1, required=False)
    strategy_code = serializers.ChoiceField(choices=("normal", "serialized"), required=False)
    stock_state = serializers.ChoiceField(
        choices=("in_stock", "out_of_stock", "low_stock"), required=False
    )
    has_reserved = serializers.BooleanField(required=False)
    ordering = serializers.CharField(required=False, allow_blank=True)


class InventoryVariantRowSerializer(serializers.Serializer):
    variant = serializers.IntegerField()
    sku = serializers.CharField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    category_id = serializers.IntegerField()
    category_name = serializers.CharField()
    strategy = InventoryStrategySerializer()
    total = serializers.IntegerField()
    sellable = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()
    min_stock = serializers.IntegerField()
    low_stock = serializers.BooleanField()
    default_warehouse = WarehouseContextSerializer()


class WarehouseQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    status = serializers.IntegerField(min_value=1, required=False)
    city = serializers.IntegerField(min_value=1, required=False)
    ordering = serializers.CharField(required=False, allow_blank=True)


class WarehouseWriteSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=100)
    city = serializers.PrimaryKeyRelatedField(queryset=Warehouse._meta.get_field("city").remote_field.model.objects.all())
    address = serializers.CharField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    phone_numbers = serializers.ListField(
        child=serializers.CharField(max_length=30, allow_blank=False), allow_empty=True
    )
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    is_default = serializers.BooleanField(required=False)
    status = serializers.PrimaryKeyRelatedField(queryset=Warehouse._meta.get_field("status").remote_field.model.objects.all())

    def validate_phone_numbers(self, values):
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise serializers.ValidationError("Phone numbers cannot be blank.")
        if len(set(normalized)) != len(normalized):
            raise serializers.ValidationError("Phone numbers must be unique.")
        return normalized


class WarehouseSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)
    state_id = serializers.IntegerField(source="city.state_id", read_only=True)
    state_name = serializers.CharField(source="city.state.name", read_only=True)
    country_id = serializers.IntegerField(source="city.state.country_id", read_only=True)
    country_name = serializers.CharField(source="city.state.country.name", read_only=True)
    status_name = serializers.CharField(source="status.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = (
            "id", "code", "name", "city", "city_name", "state_id", "state_name",
            "country_id", "country_name", "address", "lat", "lng", "phone_numbers",
            "postal_code", "is_default", "status", "status_name",
        )


class OptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class CodeOptionSerializer(OptionSerializer):
    code = serializers.CharField()
