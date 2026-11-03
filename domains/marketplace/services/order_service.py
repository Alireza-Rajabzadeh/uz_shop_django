from django.db import transaction
from django.utils.translation import gettext as _

from domains.business_payments.services import BusinessPaymentService
from domains.business.services import BusinessShipmentService
from domains.order.flow import BaseOrderService
from domains.shipment.services import ShipmentPrice

from ..models import (
    MarketplaceOrder,
    MarketplaceOrderHistory,
    MarketplaceOrderItem,
    MarketplaceOrderItemReservation,
    MarketplaceOrderStatus,
    MarketplaceOrderStatusAction,
)
from .cart_service import MarketplaceCartService
from .charge_service import MarketplaceOrderChargeService
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

    def _apply_order_charges(
        self, order, discounted_subtotal, *, shipment=None, shipment_price=None
    ):
        """Snapshot the seller's charges and the chosen shipment."""
        return MarketplaceOrderChargeService.apply(
            order, discounted_subtotal, shipment=shipment
        )

    def _charge_payload(self, order):
        return [
            {
                "id": charge.id,
                "kind": charge.kind,
                "business_charge_id": charge.business_charge_id,
                "business_shipment_id": charge.business_shipment_id,
                "name": charge.name,
                "type": charge.type,
                "calculation_type": charge.calculation_type,
                "rate": str(charge.rate),
                "amount": str(charge.amount),
            }
            for charge in order.charges.order_by("id")
        ]

    def _order_payload(self, order):
        payload = super()._order_payload(order)
        payload["totals"]["charges_total"] = str(order.charges_total)
        payload["charges"] = self._charge_payload(order)
        return payload

    def _admin_order_row(
        self, order, *, include_returns=False, include_location=False
    ):
        payload = super()._admin_order_row(
            order,
            include_returns=include_returns,
            include_location=include_location,
        )
        payload["totals"]["charges_total"] = str(order.charges_total)
        return payload

    def ongoing_orders_summary(self, limit=20):
        """This seller's ongoing orders: the full total plus the newest rows.

        Read through `_scoped_orders`, so a dashboard cannot report anybody
        else's book. `count` is the total rather than the page length: the
        panel shows it as a headline number.
        """
        orders = (
            self._scoped_orders()
            .filter(status__name__in=self.IN_PROGRESS_STATUSES)
            .select_related("status", "customer")
            .order_by("-created_at", "-id")
        )
        return {
            "count": orders.count(),
            "results": [
                self._dashboard_order_row(order) for order in orders[:limit]
            ],
        }

    def _dashboard_order_row(self, order):
        """A summary line, deliberately not `_admin_order_row`.

        The admin row carries items, available actions and charges; a summary
        row needs none of them and each one costs a query. The province and
        city are the exception: they already sit in this row's `address_info`,
        so the map can group the same orders the card lists for free.
        """
        row = {
            "id": order.id,
            "status": {
                "id": order.status_id,
                "name": order.status.name,
                "fa_name": order.status.fa_name,
            },
            "total_amount": str(order.total_amount),
            "created_at": order.created_at,
            "customer": {
                "name": (
                    f"{order.customer.first_name} {order.customer.last_name}"
                ).strip()
            },
        }
        location = self._order_location(order)
        if location is not None:
            row["location"] = location
        return row

    @transaction.atomic
    def checkout_business_from_cart(
        self, customer, business_id, shipment_id=None
    ):
        """Create one order from one seller's share of the basket.

        The cart can hold several sellers. Checkout is intentionally per
        seller: another seller's items must not block this order, and this
        seller's items must not remove the rest of the basket. If this seller
        has not configured a payment method, nothing is created and the lines
        stay in the cart so the customer can retry later.

        ``shipment_id`` is the delivery method selected in checkout. It must
        belong to the seller; omitting it uses the seller's default. When the
        seller has no usable shipment configuration, the legacy zero-price
        quote keeps the order creatable.
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

        try:
            shipment_config = BusinessShipmentService.resolve_for_checkout(
                business, shipment_id
            )
        except BusinessShipmentService.ValidationError as exc:
            raise self.ValidationError(exc.errors) from exc
        shipment_quote = None
        if shipment_config is not None:
            try:
                cost = BusinessShipmentService.calculate_price(shipment_config)
            except BusinessShipmentService.ValidationError as exc:
                raise self.ValidationError(exc.errors) from exc
            shipment_quote = ShipmentPrice(
                original_price=cost, final_price=cost
            )
        order = self._create_order(
            customer,
            cart.address_info,
            selected,
            shipment_quote=shipment_quote,
            shipment_config=shipment_config,
        )
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
