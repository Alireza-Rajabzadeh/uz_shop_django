"""Customer cart endpoints for the marketplace basket.

The cart behaviour is the shared cart behaviour; only the tables differ, so
each shop cart view is subclassed with the marketplace service. This keeps the
shop cart endpoints available to the legacy flow while every customer cart
write lands in ``marketplace_cart``.
"""

from domains.cart.views import (
    CartAddressView,
    CartClearView,
    CartItemDetail,
    CartItemMoveToPreOrder,
    CartItemMoveToWishlist,
    CartItemsView,
    CartMergeView,
    CartSyncView,
    CartValidateItemsView,
    CartValidateView,
    CartView,
)

from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.business.services.business_shipment_service import (
    BusinessShipmentService,
)

from ..services.cart_service import MarketplaceCartService
from .serializers import MarketplaceOrderChargesSerializer


class MarketplaceCartView(CartView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemsView(CartItemsView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemDetail(CartItemDetail):
    cart_service_class = MarketplaceCartService


class MarketplaceCartClearView(CartClearView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartAddressView(CartAddressView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemMoveToWishlist(CartItemMoveToWishlist):
    cart_service_class = MarketplaceCartService


class MarketplaceCartItemMoveToPreOrder(CartItemMoveToPreOrder):
    cart_service_class = MarketplaceCartService


class MarketplaceCartSyncView(CartSyncView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartValidateView(CartValidateView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartValidateItemsView(CartValidateItemsView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartMergeView(CartMergeView):
    cart_service_class = MarketplaceCartService


class MarketplaceCartChargesView(APIView):
    """Preview the shipment and other charges for one seller's basket.

    Read-only: the checkout screen uses it on its final step, and only order
    creation persists the same numbers as snapshot rows.
    """

    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = MarketplaceOrderChargesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = MarketplaceCartService()
        try:
            data = service.calculate_order_charges(
                request.user,
                serializer.validated_data["business_id"],
                serializer.validated_data.get("shipment_id"),
            )
        except service.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "", data)


class MarketplaceBusinessShipmentsView(APIView):
    """The shipment methods one seller still offers.

    Powers the radio list on checkout's address step. Only usable
    configurations are returned, and the business's default is flagged so the
    client can preselect it.
    """

    permission_classes = [IsCustomer]

    def get(self, request, business_id):
        business = BusinessProfile.objects.filter(pk=business_id).first()
        if business is None:
            raise NotFound(_("Business not found."))
        rows = []
        for shipment in BusinessShipmentService.available_shipments(business):
            try:
                cost = BusinessShipmentService.calculate_price(shipment)
            except BusinessShipmentService.ValidationError:
                continue
            rows.append({
                "id": shipment.id,
                "shipment_method": {
                    "id": shipment.shipment_method_id,
                    "code": shipment.shipment_method.code,
                    "name": shipment.shipment_method.name,
                },
                "cost": str(cost),
                "is_default": shipment.is_default,
            })
        return api_response(True, "", {"shipments": rows})
