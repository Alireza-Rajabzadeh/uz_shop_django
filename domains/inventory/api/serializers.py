from rest_framework import serializers


class WarehouseContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()


class InventoryStrategySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class NormalInventoryDetailSerializer(serializers.Serializer):
    warehouse = WarehouseContextSerializer()
    quantity = serializers.IntegerField()
    sellable = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()


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


class VariantInventoryDetailSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    strategy = InventoryStrategySerializer()
    total_item_count = serializers.IntegerField()
    sellable_item_count = serializers.IntegerField()
    available_item_count = serializers.IntegerField()
    inventory = NormalInventoryDetailSerializer(allow_null=True)
    serial_items = SerializedItemDetailSerializer(many=True, allow_null=True)
