from decimal import Decimal
from core.services.base import BaseService
from domains.catalog.models import ProductVariants
from domains.catalog.models.product_variants_details import ProductVariantsDetails


class VariantService(BaseService):
    model = ProductVariants

    def calculate_discounted_price(self, variant):
        if variant.discount_type == "percentage" and variant.discount_value:
            discount = variant.price * (variant.discount_value / Decimal(100))
            return variant.price - discount
        if variant.discount_type == "fixed" and variant.discount_value:
            return variant.price - variant.discount_value
        return variant.price

    def create_with_details(self, variant_data, details_data=None):
        variant = self.create(**variant_data)
        if details_data:
            for detail in details_data:
                ProductVariantsDetails.objects.create(variant=variant, **detail)
        return variant
