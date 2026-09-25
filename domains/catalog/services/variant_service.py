from domains.marketplace.services import MarketplacePricingService


class VariantService:
    def calculate_discounted_price(self, variant, offer=None):
        if offer is None:
            offer = getattr(variant, "_business_offer", None)
        return MarketplacePricingService.calculate_discounted_price(offer)
