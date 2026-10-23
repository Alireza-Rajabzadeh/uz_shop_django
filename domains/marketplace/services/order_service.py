from django.db import transaction
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
    seller are declared here. The basket prices each line from its best active
    offer and carries no business of its own, so the seller has to be derived
    from the lines themselves at the moment the order is created:

    * every line must still be listed, otherwise nothing can be attributed
    * every line must come from the same seller, otherwise there is no single
      business the order could belong to

    Both rules raise before the order row exists, so a rejected cart never
    leaves an order behind.
    """

    class PaymentMethodUnavailable(Exception):
        """The seller has no active payment method yet."""

        def __init__(self, business):
            self.business = business
            super().__init__(
                _("This seller has not added a payment method yet.")
            )

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

    def _has_payment_channel(self, business=None):
        return BusinessPaymentService.has_available_channel(
            business_id=getattr(business, "id", business)
        )

    def _item_extra_fields(self, variant):
        # Pin the offer the line was priced from. Totals are always read back
        # from this row, never recomputed from an offer that may have moved.
        return {"marketplace_offer": getattr(variant, "_business_offer", None)}

    def _order_extra_fields(self, items):
        return {"business": self._business_for(items)}



    @transaction.atomic
    def checkout_business_from_cart(self, customer, business_id):
        """Create one order from one seller's share of the basket.

        The cart can hold several sellers. Checkout is intentionally per
        seller: another seller's items must not block this order, and this
        seller's items must not remove the rest of the basket. If this seller
        has not configured a payment method, nothing is created and the lines
        stay in the cart so the customer can retry later.
        """
        cart, items = self._cart_for_checkout(customer)
        self._attach_line_offers(items)
        selected = [
            item
            for item in items
            if getattr(item.variant, "_business_offer", None) is not None
            and item.variant._business_offer.business_id == business_id
        ]
        if not selected:
            raise self.ValidationError({
                "cart": [_("There are no items from this seller in the cart.")]
            })
        self._validate_lines(selected)
        business = selected[0].variant._business_offer.business
        if not self._has_payment_channel(business):
            raise self.PaymentMethodUnavailable(business)
        order = self._create_order(customer, cart.address_info, selected)
        for item in selected:
            item.delete()
        return order

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
