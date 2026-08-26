from rest_framework import serializers

from domains.catalog.models import ProductVariants
from domains.inventory.enums.InventorySupplyCostTypeEnum import InventorySupplyCostTypeEnum
from domains.inventory.enums.VariantCostStrategyEnum import VariantCostStrategyEnum
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


class SupplyVariantContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()


class SupplyWarehouseContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class SupplyCostRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    description = serializers.CharField()


class SupplyListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    variant = SupplyVariantContextSerializer()
    warehouse = SupplyWarehouseContextSerializer()
    quantity = serializers.IntegerField()
    remaining_quantity = serializers.IntegerField()
    unit_buy_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    base_cost_total = serializers.DecimalField(max_digits=17, decimal_places=2)
    extra_cost_total = serializers.DecimalField(max_digits=17, decimal_places=2)
    landed_cost_total = serializers.DecimalField(max_digits=17, decimal_places=2)
    landed_unit_cost = serializers.DecimalField(max_digits=19, decimal_places=6)
    supplied_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField(allow_null=True)
    is_received = serializers.BooleanField()
    reference_number = serializers.CharField()
    invoice_number = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SupplyDetailSerializer(SupplyListSerializer):
    notes = serializers.CharField(allow_blank=True)
    costs = SupplyCostRowSerializer(many=True)


class SupplyCostTypeOptionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class SupplyCostWriteSerializer(ClosedSerializer):
    type = serializers.ChoiceField(choices=InventorySupplyCostTypeEnum.choices())
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)


class SupplyWriteSerializer(ClosedSerializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariants.objects.all(), source="variant"
    )
    warehouse_id = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), source="warehouse"
    )
    quantity = serializers.IntegerField(min_value=1)
    unit_buy_price = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0)
    supplied_at = serializers.DateTimeField()
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    invoice_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    costs = SupplyCostWriteSerializer(many=True, required=False)


class SupplyQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    variant_id = serializers.IntegerField(min_value=1, required=False)
    warehouse_id = serializers.IntegerField(min_value=1, required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    has_remaining = serializers.BooleanField(
        required=False, default=None, allow_null=True
    )
    received = serializers.BooleanField(
        required=False, default=None, allow_null=True
    )
    ordering = serializers.CharField(required=False, allow_blank=True)


class SupplyReceiveSerialItemSerializer(ClosedSerializer):
    serial_number = serializers.CharField(max_length=100, trim_whitespace=False)


class SupplyReceiveSerializer(ClosedSerializer):
    serial_items = SupplyReceiveSerialItemSerializer(many=True, required=False)


class PricingStrategyOptionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class VariantPricingWriteSerializer(ClosedSerializer):
    expected_profit_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, required=False
    )
    cost_strategy = serializers.ChoiceField(
        choices=VariantCostStrategyEnum.choices(), required=False
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs:
            raise serializers.ValidationError(
                "Submit at least one pricing field to update."
            )
        return attrs


class VariantPriceApplySerializer(ClosedSerializer):
    price = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=0,
        required=False,
    )


class VariantPriceHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    old_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    new_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    cost_basis = serializers.DecimalField(max_digits=17, decimal_places=2)
    cost_strategy = serializers.CharField()
    expected_profit_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
    )
    source = serializers.CharField()
    created_at = serializers.DateTimeField()


class VariantPricingOverviewSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    latest_cost = serializers.DecimalField(max_digits=17, decimal_places=2, allow_null=True)
    weighted_average_cost = serializers.DecimalField(
        max_digits=17, decimal_places=2, allow_null=True
    )
    fifo_next_cost = serializers.DecimalField(
        max_digits=17, decimal_places=2, allow_null=True
    )
    cost_strategy = serializers.CharField(allow_null=True)
    expected_profit_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    cost_basis = serializers.DecimalField(max_digits=17, decimal_places=2, allow_null=True)
    suggested_price = serializers.DecimalField(
        max_digits=19, decimal_places=2, allow_null=True
    )
    total_remaining_supply_quantity = serializers.IntegerField()
    catalog_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, allow_null=True
    )
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)


class PricingListRowSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    cost_strategy = serializers.CharField(allow_null=True)
    expected_profit_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    cost_basis = serializers.DecimalField(max_digits=17, decimal_places=2, allow_null=True)
    suggested_price = serializers.DecimalField(
        max_digits=19, decimal_places=2, allow_null=True
    )
    remaining_quantity = serializers.IntegerField()


class PricingQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.IntegerField(min_value=1, required=False)
    strategy = serializers.ChoiceField(
        choices=VariantCostStrategyEnum.choices(), required=False
    )
    has_pricing = serializers.BooleanField(
        required=False, default=None, allow_null=True
    )
    ordering = serializers.CharField(required=False, allow_blank=True)


class InventoryReportSummarySerializer(serializers.Serializer):
    inventory_cost_value = serializers.DecimalField(max_digits=30, decimal_places=2)
    remaining_supply_quantity = serializers.IntegerField()
    total_cogs = serializers.DecimalField(max_digits=22, decimal_places=2)
    estimated_revenue = serializers.DecimalField(max_digits=30, decimal_places=2)
    estimated_profit = serializers.DecimalField(max_digits=30, decimal_places=2)


class ReportVariantRowSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()
    remaining_quantity = serializers.IntegerField()
    inventory_cost_value = serializers.DecimalField(max_digits=30, decimal_places=2)
    average_remaining_cost = serializers.DecimalField(
        max_digits=19, decimal_places=2, allow_null=True
    )
    total_consumed_quantity = serializers.IntegerField()
    total_cogs = serializers.DecimalField(max_digits=22, decimal_places=2)
    current_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, allow_null=True
    )
    suggested_price = serializers.DecimalField(
        max_digits=19, decimal_places=2, allow_null=True
    )


class ReportVariantQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.IntegerField(min_value=1, required=False)
    strategy = serializers.ChoiceField(
        choices=VariantCostStrategyEnum.choices(), required=False
    )
    ordering = serializers.CharField(required=False, allow_blank=True)


class ReportSupplyVariantContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()


class ReportSupplyWarehouseContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class ReportSupplyRowSerializer(serializers.Serializer):
    supply_id = serializers.IntegerField()
    variant = ReportSupplyVariantContextSerializer()
    warehouse = ReportSupplyWarehouseContextSerializer()
    original_quantity = serializers.IntegerField()
    remaining_quantity = serializers.IntegerField()
    consumed_quantity = serializers.IntegerField()
    unit_buy_price = serializers.DecimalField(max_digits=15, decimal_places=2)
    landed_unit_cost = serializers.DecimalField(max_digits=19, decimal_places=2)
    original_cost_value = serializers.DecimalField(max_digits=21, decimal_places=2)
    remaining_cost_value = serializers.DecimalField(max_digits=21, decimal_places=2)
    consumed_cost_value = serializers.DecimalField(max_digits=21, decimal_places=2)


class ReportSupplyQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    ordering = serializers.CharField(required=False, allow_blank=True)
