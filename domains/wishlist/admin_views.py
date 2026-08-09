from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.users.auth import AdminJWTAuthentication

from .models import Wishlist
from .serializers import AdminWishlistListQuerySerializer, AdminWishlistSerializer
from .services import WishlistService


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminWishlistList(AdminAPIView):
    model = Wishlist

    def get(self, request):
        query = AdminWishlistListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        items = WishlistService().list_admin(**query.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        data = AdminWishlistSerializer(page, many=True).data
        return api_response(True, "", paginator.get_paginated_response(data).data)


class AdminWishlistDetail(AdminAPIView):
    model = Wishlist

    def get(self, request, wishlist_id):
        try:
            item = Wishlist.objects.select_related(
                "customer", "product", "product__status", "product__brand"
            ).prefetch_related("product__categories").get(id=wishlist_id)
        except Wishlist.DoesNotExist as exc:
            raise NotFound(_("Wishlist item not found.")) from exc
        return api_response(True, "", AdminWishlistSerializer(item).data)
