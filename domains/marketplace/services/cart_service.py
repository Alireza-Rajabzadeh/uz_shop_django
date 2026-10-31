from decimal import Decimal

from django.utils.translation import gettext as _

from domains.business.models import BusinessProfile
from domains.business.services import BusinessShipmentService
from domains.cart.services import BaseCartService

from ..models import MarketplaceCart, MarketplaceCartItem
from .charge_service import MarketplaceOrderChargeService


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

    def calculate_order_charges(self, customer, business_id, shipment_id=None):
        """Preview the seller's shipment and other charges for this basket.

        Nothing is persisted: the checkout screen calls this after the
        address step to show the final amounts, and order creation snapshots
        the same calculation. The discounted subtotal is the sum of this
        seller's ``line_total`` values, which already equal
        ``unit_price * quantity - discount`` per line.
        """
        payload = self.describe_cart(customer)
        business_items = [
            item
            for item in payload["items"]
            if (item.get("business") or {}).get("id") == business_id
        ]
        if not business_items:
            raise self.ValidationError({
                "cart": [_("There are no items from this seller in the cart.")]
            })

        business = BusinessProfile.objects.filter(pk=business_id).first()
        if business is None:
            raise self.ValidationError({
                "business": [_("Business not found.")]
            })

        discounted_subtotal = sum(
            (Decimal(item["line_total"]) for item in business_items),
            Decimal("0.00"),
        )
        try:
            shipment = BusinessShipmentService.resolve_for_checkout(
                business, shipment_id
            )
        except BusinessShipmentService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc

        charges = MarketplaceOrderChargeService.calculate_order_charges(
            business, discounted_subtotal, shipment=shipment
        )
        charges["subtotal"] = str(discounted_subtotal.quantize(Decimal("0.01")))
        charges["discount_amount"] = str(
            sum(
                (Decimal(item["line_discount"]) for item in business_items),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"))
        )
        return charges
