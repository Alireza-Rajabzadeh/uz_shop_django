from rest_framework import serializers

from .models import Wishlist


class WishlistWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class WishlistQuerySerializer(serializers.Serializer):
    product_id = serializers.IntegerField()


class WishlistSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ["id", "product_id", "product", "created_at"]
        read_only_fields = ["id", "product_id", "created_at"]

    def get_product(self, obj):
        product = obj.product
        primary_category = product.categories.order_by("id").first() if product else None
        return {
            "id": product.id,
            "slug": product.slug,
            "name": product.name,
            "status": product.status.name,
            "brand": {"id": product.brand_id, "name": product.brand.name}
            if product.brand_id else None,
            "category": {"id": primary_category.id, "name": primary_category.name}
            if primary_category else None,
        }