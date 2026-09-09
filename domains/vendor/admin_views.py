from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.serializers import (
    AdminVendorListQuerySerializer,
    AdminVendorSerializer,
    VendorStatusSerializer,
)
from domains.vendor.services.vendor_service import VendorService
from domains.users.auth import AdminJWTAuthentication


vendor_service = VendorService()


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminVendorList(AdminAPIView):
    model = Vendor

    def get(self, request):
        query = AdminVendorListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        vendors = vendor_service.search(
            ordering=values.pop("ordering", None),
            search=values.pop("search", None),
            **values,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(vendors, request, view=self)
        data = AdminVendorSerializer(page, many=True).data
        return api_response(True, "", paginator.get_paginated_response(data).data)


class AdminVendorDetail(AdminAPIView):
    model = Vendor

    def get_object(self, vendor_id):
        vendor = vendor_service.get_vendor(vendor_id)
        if vendor is None:
            raise NotFound(_("Vendor not found."))
        return vendor

    def get(self, request, vendor_id):
        return api_response(True, "", AdminVendorSerializer(self.get_object(vendor_id)).data)

    def patch(self, request, vendor_id):
        vendor = self.get_object(vendor_id)
        serializer = AdminVendorSerializer(vendor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vendor_service.update_vendor(vendor, **serializer.validated_data)
        return api_response(True, _("Vendor updated."), AdminVendorSerializer(vendor).data)


class AdminVendorStatusList(AdminAPIView):
    model = Vendor

    def get(self, request):
        statuses = VendorStatus.objects.order_by("id")
        return api_response(True, "", VendorStatusSerializer(statuses, many=True).data)
