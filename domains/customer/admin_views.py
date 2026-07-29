from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

from core.permissions import AdminModelPermissions
from core.responses import api_response
from domains.customer.models import Customer, CustomerAddress, CustomerStatus
from domains.customer.serializers import (
    AdminCustomerListQuerySerializer,
    AdminCustomerSerializer,
    CustomerAddressSerializer,
    CustomerStatusSerializer,
)
from domains.customer.services.address_service import CustomerAddressService
from domains.customer.services.customer_service import CustomerService
from domains.users.auth import AdminJWTAuthentication


customer_service = CustomerService()
address_service = CustomerAddressService()


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [AdminModelPermissions]


class AdminCustomerList(AdminAPIView):
    model = Customer

    def get(self, request):
        query = AdminCustomerListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        values = query.validated_data.copy()
        customers = customer_service.search(
            ordering=values.pop("ordering", None),
            search=values.pop("search", None),
            **values,
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(customers, request, view=self)
        data = AdminCustomerSerializer(page, many=True).data
        return api_response(True, "", paginator.get_paginated_response(data).data)


class AdminCustomerDetail(AdminAPIView):
    model = Customer

    def get_object(self, customer_id):
        customer = customer_service.get_customer(customer_id)
        if customer is None:
            raise NotFound(_("Customer not found."))
        return customer

    def get(self, request, customer_id):
        return api_response(True, "", AdminCustomerSerializer(self.get_object(customer_id)).data)

    def patch(self, request, customer_id):
        customer = self.get_object(customer_id)
        serializer = AdminCustomerSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer_service.update_customer(customer, **serializer.validated_data)
        return api_response(True, _("Customer updated."), AdminCustomerSerializer(customer).data)


class AdminCustomerStatusList(AdminAPIView):
    # Statuses are supporting options for the customer form, so viewing
    # customers is sufficient to populate this endpoint.
    model = Customer

    def get(self, request):
        statuses = CustomerStatus.objects.order_by("id")
        return api_response(True, "", CustomerStatusSerializer(statuses, many=True).data)


class AdminCustomerAddressListCreate(AdminAPIView):
    model = CustomerAddress

    def get_customer(self, customer_id):
        customer = customer_service.get_customer(customer_id)
        if customer is None:
            raise NotFound(_("Customer not found."))
        return customer

    def get(self, request, customer_id):
        addresses = address_service.list_for_customer(self.get_customer(customer_id))
        return api_response(True, "", CustomerAddressSerializer(addresses, many=True).data)

    def post(self, request, customer_id):
        customer = self.get_customer(customer_id)
        serializer = CustomerAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = address_service.create(customer=customer, **serializer.validated_data)
        return api_response(
            True, _("Address created."), CustomerAddressSerializer(address).data, status_code=201
        )


class AdminCustomerAddressDetail(AdminAPIView):
    model = CustomerAddress

    def get_object(self, customer_id, address_id):
        address = address_service.get_for_customer(
            Customer(pk=customer_id), address_id
        )
        if address is None:
            raise NotFound(_("Address not found."))
        return address

    def get(self, request, customer_id, address_id):
        return api_response(
            True, "", CustomerAddressSerializer(self.get_object(customer_id, address_id)).data
        )

    def patch(self, request, customer_id, address_id):
        address = self.get_object(customer_id, address_id)
        serializer = CustomerAddressSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        address_service.update(address, **serializer.validated_data)
        return api_response(True, _("Address updated."), CustomerAddressSerializer(address).data)

    def delete(self, request, customer_id, address_id):
        address_service.delete(self.get_object(customer_id, address_id))
        return api_response(True, _("Address deleted."), None)
