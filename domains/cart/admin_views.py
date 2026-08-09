from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import Cart
from .serializers import AdminCartListQuerySerializer
from .services import CartService


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminCartList(AdminAPIView):
    model = Cart

    def get(self, request):
        query = AdminCartListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        carts = CartService().list_admin(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(carts, request, view=self)
        rows = [CartService._admin_cart_row(cart) for cart in page]
        return api_response(True, "", paginator.get_paginated_response(rows).data)


class AdminCartDetail(AdminAPIView):
    model = Cart

    def get(self, request, cart_id):
        try:
            payload = CartService().cart_payload_admin(cart_id)
        except CartService.ValidationError as exc:
            raise NotFound(exc.errors["cart"][0]) from exc
        return api_response(True, "", payload)
