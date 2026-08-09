from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import PreOrder
from .serializers import AdminPreOrderListQuerySerializer, AdminPreOrderSerializer
from .services import PreOrderService


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminPreOrderList(AdminAPIView):
    model = PreOrder

    def get(self, request):
        query = AdminPreOrderListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        items = PreOrderService().list_admin(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        data = AdminPreOrderSerializer(page, many=True).data
        return api_response(True, "", paginator.get_paginated_response(data).data)


class AdminPreOrderDetail(AdminAPIView):
    model = PreOrder

    def get(self, request, preorder_id):
        try:
            item = PreOrder.objects.select_related(
                "customer", "product", "product__status", "product__brand"
            ).prefetch_related("product__categories").get(id=preorder_id)
        except PreOrder.DoesNotExist as exc:
            raise NotFound(_("Pre-order item not found.")) from exc
        return api_response(True, "", AdminPreOrderSerializer(item).data)
