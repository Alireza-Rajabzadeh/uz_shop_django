from rest_framework import serializers

from .models import Wishlist


class AdminWishlistListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    product_id = serializers.IntegerField(required=False, min_value=1)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    ordering = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if (
            attrs.get("created_from") is not None
            and attrs.get("created_to") is not None
            and attrs["created_from"] > attrs["created_to"]
        ):
            raise serializers.ValidationError(
                {"created_to": "Must be on or after the start date."}
            )
        return attrs


class AdminWishlistSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    product = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ["id", "customer", "product_id", "product", "created_at"]
        read_only_fields = fields

    def get_customer(self, obj):
        customer = obj.customer
        return {
            "id": customer.id,
            "name": f"{customer.first_name} {customer.last_name}".strip(),
            "phone": customer.phone,
            "customer_code": customer.customer_code,
        }

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