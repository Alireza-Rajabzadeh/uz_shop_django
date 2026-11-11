from ..models import Cart, CartItem
from .base_cart_service import BaseCartService


class CartService(BaseCartService):
    """The shop cart: one basket per customer, priced by the selected offer."""

    cart_model = Cart
    item_model = CartItem
    offer_field = "offer"
