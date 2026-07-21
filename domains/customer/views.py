from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound
from core.responses import api_response
from .serializers import (
    CustomerRegisterSerializer,
    CustomerLoginSerializer,
    CustomerProfileSerializer,
    CustomerUpdateSerializer,
    CustomerAddressSerializer,
)
from .services.auth_service import CustomerAuthService
from .services.address_service import CustomerAddressService
from .models import CustomerPreference


class CustomerRegister(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        result = service.register(serializer.validated_data)

        return api_response(True, "Registration successful.", result, status_code=201)


class CustomerLogin(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        result = service.login(
            serializer.validated_data["phone"],
            serializer.validated_data["password"],
        )

        return api_response(True, "Login successful.", result)


class CustomerMe(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CustomerProfileSerializer(request.user)
        return api_response(True, "", serializer.data)

    def patch(self, request):
        serializer = CustomerUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        result = service.update_profile(request.user, serializer.validated_data)

        return api_response(True, "Profile updated.", result)


class CustomerAddressListCreate(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        service = CustomerAddressService()
        addresses = service.list_for_customer(request.user)
        serializer = CustomerAddressSerializer(addresses, many=True)
        return api_response(True, "", serializer.data)

    def post(self, request):
        serializer = CustomerAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAddressService()
        address = service.create(customer=request.user, **serializer.validated_data)
        result = CustomerAddressSerializer(address).data

        return api_response(True, "Address created.", result, status_code=201)


class CustomerAddressDetail(APIView):
    permission_classes = [IsAuthenticated]

    def _get_address(self, customer, address_id):
        service = CustomerAddressService()
        address = service.get_or_none(address_id)
        if address is None or address.customer_id != customer.id:
            raise NotFound("Address not found.")
        return address

    def get(self, request, address_id):
        address = self._get_address(request.user, address_id)
        serializer = CustomerAddressSerializer(address)
        return api_response(True, "", serializer.data)

    def patch(self, request, address_id):
        address = self._get_address(request.user, address_id)
        serializer = CustomerAddressSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        service = CustomerAddressService()
        service.update(address, **serializer.validated_data)
        result = CustomerAddressSerializer(address).data

        return api_response(True, "Address updated.", result)

    def delete(self, request, address_id):
        address = self._get_address(request.user, address_id)
        service = CustomerAddressService()
        service.delete(address)
        return api_response(True, "Address deleted.", None)


class CustomerPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        preference, _ = CustomerPreference.objects.get_or_create(customer=request.user)
        return api_response(True, "", {
            "receive_order_emails": preference.receive_order_emails,
            "receive_sms_notifications": preference.receive_sms_notifications,
            "receive_push_notifications": preference.receive_push_notifications,
        })

    def patch(self, request):
        preference, _ = CustomerPreference.objects.get_or_create(customer=request.user)
        allowed = ["receive_order_emails", "receive_sms_notifications", "receive_push_notifications"]
        for field in allowed:
            if field in request.data:
                setattr(preference, field, request.data[field])
        preference.save()
        return api_response(True, "Preferences updated.", {
            "receive_order_emails": preference.receive_order_emails,
            "receive_sms_notifications": preference.receive_sms_notifications,
            "receive_push_notifications": preference.receive_push_notifications,
        })
