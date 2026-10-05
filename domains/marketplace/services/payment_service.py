"""Paying a marketplace order.

Submitting, reviewing and recording a payment is inherited from
``BusinessPaymentService``: the method rules, the channel rules, the document
rules and the review state machine are the same whoever the order belongs to.
What differs is only the rows written, so this names the marketplace tables
and points the hold machinery at the marketplace order service.
"""

from domains.business_payments.services import BusinessPaymentService

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderAction,
    MarketplaceOrderHistory,
    MarketplaceOrderPayment,
    MarketplaceOrderStatus,
    MarketplacePaymentDocument,
)
from .order_service import MarketplaceOrderService


class MarketplacePaymentService(BusinessPaymentService):
    order_model = MarketplaceOrder
    order_status_model = MarketplaceOrderStatus
    payment_model = MarketplaceOrderPayment
    payment_document_model = MarketplacePaymentDocument
    history_model = MarketplaceOrderHistory
    action_model = MarketplaceOrderAction

    def order_service(self):
        return MarketplaceOrderService()
