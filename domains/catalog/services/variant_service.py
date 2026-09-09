from decimal import Decimal


class VariantService:
    def calculate_discounted_price(self, variant, offer=None):
        if offer is None:
            offer = getattr(variant, "_business_offer", None)
        if offer is None:
            return Decimal("0")
        if offer.discount_type == "percentage" and offer.discount_value:
            discount = offer.price * (offer.discount_value / Decimal(100))
            return offer.price - discount
        if offer.discount_type == "fixed" and offer.discount_value:
            return offer.price - offer.discount_value
        return offer.price
