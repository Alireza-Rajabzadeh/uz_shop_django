from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import IsCustomer
from core.responses import api_response

from .serializers import (
    WishlistQuerySerializer,
    WishlistSerializer,
    WishlistWriteSerializer,
)
from .services import WishlistService


class WishlistListCreate(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        paginator = PageNumberPagination()
        items = paginator.paginate_queryset(
            WishlistService().list_for_customer(request.user), request
        )
        serializer = WishlistSerializer(items, many=True)
        return api_response(
            True,
            "",
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
            },
        )

    def post(self, request):
        serializer = WishlistWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = WishlistService().add(
                request.user, serializer.validated_data["product_id"]
            )
        except WishlistService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(
            True,
            _("Added to wishlist."),
            WishlistSerializer(item).data,
            status_code=201,
        )


class WishlistExists(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        serializer = WishlistQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]
        return api_response(
            True,
            "",
            {
                "product_id": product_id,
                "in_wishlist": WishlistService().exists(request.user, product_id),
            },
        )


class WishlistRemove(APIView):
    permission_classes = [IsCustomer]

    def delete(self, request, product_id):
        try:
            WishlistService().remove(request.user, product_id)
        except WishlistService.ValidationError as exc:
            raise NotFound(exc.errors["product_id"][0]) from exc
        return api_response(True, _("Removed from wishlist."), None)