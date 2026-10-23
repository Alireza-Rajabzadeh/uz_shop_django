from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response

from .address import AddressInfoService, CartAddressWriteSerializer
from .serializers import (
    CartItemAddSerializer,
    CartItemQuantitySerializer,
    CartSyncSerializer,
)
from .services import CartService


def _map_errors(exc):
    raise ValidationError(exc.errors) from exc


class CartView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def get(self, request):
        return api_response(True, "", self.cart_service_class().describe_cart(request.user))


class CartItemsView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data.get("quantity", 1)
        offer_id = serializer.validated_data.get("offer_id")
        service = self.cart_service_class()
        try:
            service.add(
                request.user,
                serializer.validated_data["variant_id"],
                quantity,
                offer_id=offer_id,
            )
        except self.cart_service_class.ValidationError as exc:
            _map_errors(exc)
        return api_response(True, _("Added to cart."), service.describe_cart(request.user), status_code=201)


class CartItemDetail(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def _get_item(self, request, item_id):
        try:
            return self.cart_service_class().get_item(request.user, item_id)
        except self.cart_service_class.ValidationError as exc:
            raise NotFound(exc.errors["item"][0]) from exc

    def patch(self, request, item_id):
        serializer = CartItemQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self.cart_service_class()
        try:
            service.update_quantity(
                request.user, item_id, serializer.validated_data["quantity"]
            )
        except self.cart_service_class.ValidationError as exc:
            _map_errors(exc)
        return api_response(True, _("Quantity updated."), service.describe_cart(request.user))

    def delete(self, request, item_id):
        self._get_item(request, item_id)
        service = self.cart_service_class()
        try:
            service.remove(request.user, item_id)
        except self.cart_service_class.ValidationError as exc:
            raise NotFound(exc.errors["item"][0]) from exc
        return api_response(True, _("Removed from cart."), service.describe_cart(request.user))


class CartClearView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request):
        service = self.cart_service_class()
        service.clear(request.user)
        return api_response(True, _("Cart cleared."), service.describe_cart(request.user))


class CartAddressView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def put(self, request):
        serializer = CartAddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            info = self.cart_service_class().set_address(request.user, serializer.validated_data)
        except (self.cart_service_class.ValidationError, AddressInfoService.ValidationError) as exc:
            _map_errors(exc)
        return api_response(True, _("Address updated."), info)


class CartItemMoveToWishlist(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request, item_id):
        try:
            result = self.cart_service_class().move_to_wishlist(request.user, item_id)
        except self.cart_service_class.ValidationError as exc:
            raise NotFound(exc.errors["item"][0]) from exc
        return api_response(True, _("Moved to wishlist."), result)


class CartItemMoveToPreOrder(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request, item_id):
        try:
            result = self.cart_service_class().move_to_preorder(request.user, item_id)
        except self.cart_service_class.ValidationError as exc:
            if "item" in exc.errors:
                raise NotFound(exc.errors["item"][0]) from exc
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Moved to pre-order list."), result)


class CartSyncView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request):
        serializer = CartSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self.cart_service_class().sync(
            request.user, serializer.validated_data.get("items", [])
        )
        return api_response(True, _("Cart synchronized."), result)


class CartValidateView(APIView):
    cart_service_class = CartService

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsCustomer()]

    def get(self, request):
        data = self.cart_service_class().describe_cart(request.user)
        summary = {
            "valid": data["cart_valid"],
            "totals": data["totals"],
            "items": [
                {
                    "id": item["id"],
                    "variant_id": item["variant_id"],
                    "business": item["business"],
                    "quantity": item["quantity"],
                    "product_name": item["product_name"],
                    "status": item["status"],
                    "reason": item["reason"] or None,
                    "valid": item["valid"],
                    "suggested_action": item["suggested_action"],
                }
                for item in data["items"]
            ],
        }
        return api_response(True, "", summary)

    def post(self, request):
        """Validate a single variant/quantity without persisting a cart."""
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = self.cart_service_class().validate_variant(
            serializer.validated_data["variant_id"],
            serializer.validated_data.get("quantity", 1),
            serializer.validated_data.get("offer_id"),
        )
        return api_response(True, "", payload)


class CartValidateItemsView(APIView):
    permission_classes = [AllowAny]
    cart_service_class = CartService

    def post(self, request):
        """Bulk-validate a guest cart without persisting anything."""
        serializer = CartSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = self.cart_service_class().validate_items(serializer.validated_data.get("items", []))
        return api_response(True, "", {"items": items})


class CartMergeView(APIView):
    permission_classes = [IsCustomer]
    cart_service_class = CartService

    def post(self, request):
        """Merge a guest cart into the customer's persisted cart."""
        serializer = CartSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self.cart_service_class().merge(
            request.user, serializer.validated_data.get("items", [])
        )
        return api_response(True, _("Cart merged."), result)