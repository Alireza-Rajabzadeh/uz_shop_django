from django.utils.translation import gettext as _

from domains.business_payments.services import BusinessPaymentService
from domains.cart.checkout import BaseCheckoutService, CheckoutError

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderItem,
    MarketplaceOrderItemReservation,
    MarketplaceOrderStatus,
)
from .cart_service import MarketplaceCartService


class MarketplaceOrderService(BaseCheckoutService):
    """The marketplace flow, writing the marketplace tables.

    How an order is created is inherited wholesale; only the tables and the
    two rules that exist purely because a marketplace order belongs to a
    seller are declared here. The basket is priced from every active offer
    because the business is a singleton today, so the seller has to be
    derived from the lines themselves at the moment the order is created:

    * every line must still be listed, otherwise nothing can be attributed
    * every line must come from the same seller, otherwise there is no single
      business the order could belong to

    Both rules raise before the order row exists, so a rejected cart never
    leaves an order behind.
    """

    ValidationError = CheckoutError

    order_model = MarketplaceOrder
    item_model = MarketplaceOrderItem
    reservation_model = MarketplaceOrderItemReservation
    status_model = MarketplaceOrderStatus

    @staticmethod
    def cart_service():
        return MarketplaceCartService()

    def _has_payment_channel(self):
        return BusinessPaymentService.has_available_channel()

    def _item_extra_fields(self, variant):
        # Pin the offer the line was priced from. Totals are always read back
        # from this row, never recomputed from an offer that may have moved.
        return {"marketplace_offer": getattr(variant, "_business_offer", None)}

    def _order_extra_fields(self, items):
        return {"business": self._business_for(items)}

    def _business_for(self, items):
        missing = [
            _("Item %(sku)s is no longer listed by the seller.")
            % {"sku": item.variant.sku}
            for item in items
            if getattr(item.variant, "_business_offer", None) is None
        ]
        if missing:
            raise self.ValidationError({"items": missing})

        sellers = {}
        for item in items:
            offer = item.variant._business_offer
            sellers.setdefault(offer.business_id, offer.business)
        if len(sellers) > 1:
            raise self.ValidationError({
                "items": [
                    _("The basket contains items from more than one seller.")
                ]
            })
        return next(iter(sellers.values()))
