"""Asking for a returned marketplace item.

The window, the one-open-request rule, the quantity check and the cost-layer
restoration all come from ``BaseReturnRequestService``; this names the
marketplace tables so a marketplace return cannot be written against a shop
order, and dates delivery from the marketplace audit trail.
"""

from domains.order.return_flow import BaseReturnRequestService

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderHistory,
    MarketplaceOrderItem,
    MarketplaceReturnRequest,
    MarketplaceReturnRequestEvidence,
    MarketplaceReturnRequestItem,
)


class MarketplaceReturnRequestService(BaseReturnRequestService):
    order_model = MarketplaceOrder
    order_item_model = MarketplaceOrderItem
    request_model = MarketplaceReturnRequest
    item_model = MarketplaceReturnRequestItem
    evidence_model = MarketplaceReturnRequestEvidence
    history_model = MarketplaceOrderHistory

    def __init__(self, business=None):
        """Decide on one seller's return requests.

        A return row carries no business of its own; it inherits its
        seller through the order it belongs to. Passing nothing keeps the
        platform's administrative decisions unrestricted.
        """
        self.business = business

    def _scoped_requests(self):
        queryset = super()._scoped_requests()
        if self.business is None:
            return queryset
        return queryset.filter(order__business=self.business)
