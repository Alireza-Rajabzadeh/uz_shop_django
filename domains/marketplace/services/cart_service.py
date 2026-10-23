from domains.cart.services import BaseCartService

from ..models import MarketplaceCart, MarketplaceCartItem


class MarketplaceCartService(BaseCartService):
    """The marketplace basket.

    Everything behavioural is inherited from ``BaseCartService``: the two
    baskets differ only in the tables they write, so a rule restated here
    would be a rule that could drift from the shop cart. A marketplace-specific
    rule belongs here as an override, never as a copy.

    Pricing selects the best active offer for each line unless the customer
    explicitly pinned one. The pin lets the storefront keep the selected
    seller when the same variant is offered by several businesses.
    """

    cart_model = MarketplaceCart
    item_model = MarketplaceCartItem
    offer_field = "offer"
