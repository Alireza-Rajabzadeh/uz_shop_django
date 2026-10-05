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
