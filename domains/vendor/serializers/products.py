from rest_framework import serializers

from domains.catalog.api.serializers import (
    ProductListSerializer,
    ProductDetailReadSerializer,
    ProductVariantSerializer,
)
from domains.catalog.services import ProductService
from domains.vendor.services.vendor_product_service import VendorProductService


product_service = ProductService()


class VendorProductSimilarSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    brand = serializers.DictField(allow_null=True)
    categories = serializers.ListField(child=serializers.DictField())
    status_name = serializers.CharField(allow_null=True)
    similarity = serializers.IntegerField()
    exact = serializers.BooleanField()
    thumbnail_url = serializers.URLField(allow_null=True)


class VendorProductListSerializer(ProductListSerializer):
    created_by_me = serializers.BooleanField(read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["created_by_me"]


class VendorProductDetailSerializer(ProductDetailReadSerializer):
    created_by_me = serializers.BooleanField(read_only=True)
    # Re-declared: the catalog base exposes every variant on the product, and
    # a vendor sees the shared rows plus only its own unconfirmed draft. Built
    # from the same service call as the variant list endpoint so the two can
    # never disagree on the set or on the stock counts.
    variants = serializers.SerializerMethodField()

    class Meta(ProductDetailReadSerializer.Meta):
        fields = ProductDetailReadSerializer.Meta.fields + ["created_by_me"]

    def get_variants(self, obj):
        queryset = product_service.list_product_variants(obj)
        vendor = self.context.get("vendor")
        if vendor is not None:
            queryset = VendorProductService.visible_variants(queryset, vendor)
        return ProductVariantSerializer(queryset, many=True).data
