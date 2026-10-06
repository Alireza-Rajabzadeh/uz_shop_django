from django.utils.translation import gettext as _

from domains.business_payments.services import BusinessPaymentService
from domains.order.flow import BaseOrderService

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderHistory,
    MarketplaceOrderItem,
    MarketplaceOrderItemReservation,
    MarketplaceOrderStatus,
    MarketplaceOrderStatusAction,
)
from .cart_service import MarketplaceCartService
from .return_service import MarketplaceReturnRequestService


class MarketplaceOrderService(BaseOrderService):
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

    order_model = MarketplaceOrder
    item_model = MarketplaceOrderItem
    reservation_model = MarketplaceOrderItemReservation
    status_model = MarketplaceOrderStatus
    status_action_model = MarketplaceOrderStatusAction
    history_model = MarketplaceOrderHistory

    def __init__(self, business=None):
        """Act for one seller's orders.

        ``business`` is what narrows the table. The platform's own reads pass
        nothing and keep the unrestricted behaviour they always had.
        """
        self.business = business

    def _scoped_orders(self):
        queryset = super()._scoped_orders()
        if self.business is None:
            return queryset
        return queryset.filter(business=self.business)

    @staticmethod
    def cart_service():
        return MarketplaceCartService()

    def return_service(self):
        return MarketplaceReturnRequestService

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
