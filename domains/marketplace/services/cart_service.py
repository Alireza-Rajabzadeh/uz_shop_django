from domains.cart.services import BaseCartService

from ..models import MarketplaceCart, MarketplaceCartItem


class MarketplaceCartService(BaseCartService):
    """The marketplace basket.

    Everything behavioural is inherited from ``BaseCartService``: the two
    baskets differ only in the tables they write, so a rule restated here
    would be a rule that could drift from the shop cart. A marketplace-specific
    rule belongs here as an override, never as a copy.

    Pricing reads the same active offers the shop cart reads, because the
    business is a singleton today and the cart deliberately carries no
    business of its own. Checkout is what pins each order to the business its
    offers came from.
    """

    cart_model = MarketplaceCart
    item_model = MarketplaceCartItem
