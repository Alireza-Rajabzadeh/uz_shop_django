from decimal import Decimal


class VariantService:
    def calculate_discounted_price(self, variant):
        if variant.discount_type == "percentage" and variant.discount_value:
            discount = variant.price * (variant.discount_value / Decimal(100))
            return variant.price - discount
        if variant.discount_type == "fixed" and variant.discount_value:
            return variant.price - variant.discount_value
        return variant.price
