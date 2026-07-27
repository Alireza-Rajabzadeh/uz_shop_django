from django.shortcuts import get_object_or_404
from django.db.models import Count
from core.services.base import BaseService
from domains.catalog.models import Product, ProductVariants
from domains.catalog.models.product_details import ProductDetails


class ProductService(BaseService):
    model = Product

    def create_product(self, **data):
        return self._create(**data)

    def update_product(self, instance, **data):
        return self._update(instance, **data)

    def delete_product(self, instance):
        self._delete(instance)

    def get_product(self, id):
        return self._get(id)

    def search_products(self, ordering=None, **filters):
        ordering_fields = {
            "id": "id",
            "name": "name",
            "category_name": "category__name",
            "status_name": "status__name",
            "variant_count": "variant_count",
        }
        queryset = (
            self.model.objects.filter(**filters)
            .select_related("category", "status")
            .annotate(variant_count=Count("products"))
        )
        descending = ordering and ordering.startswith("-")
        requested_field = ordering.lstrip("-") if ordering else "id"
        order_field = ordering_fields.get(requested_field, "id")
        return queryset.order_by(f"-{order_field}" if descending else order_field)

    def list_by_category(self, category_id):
        return self.model.objects.filter(category_id=category_id)

    def add_detail_to_product(self, product, details_data):
        instances = []
        for item in details_data:
            obj, _ = ProductDetails.objects.update_or_create(
                product=product,
                detail_id=item["detail_id"],
                defaults={"value": item.get("value", ""), "extra_value": item.get("extra_value")},
            )
            instances.append(obj)
        return instances

    def list_product_details(self, product):
        return ProductDetails.objects.filter(product=product).select_related("detail")

    def add_variant_to_product(self, product, **variant_data):
        return ProductVariants.objects.create(product=product, **variant_data)

    def list_product_variants(self, product):
        return ProductVariants.objects.filter(product=product)

    def get_variant(self, id):
        return get_object_or_404(ProductVariants, id=id)

    def update_variant(self, instance, **data):
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def delete_variant(self, instance):
        instance.delete()

    def search_variants(self, **filters):
        return ProductVariants.objects.filter(**filters)
