from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import APIException, NotFound, Throttled, ValidationError
from core.responses import api_response
from domains.customer.auth import CustomerJWTAuthentication
from domains.location.models import City, Country, State
from domains.location.api.options import (
    CountryOptionSerializer,
    StateOptionSerializer,
    CityOptionSerializer,
    CountryFilterSerializer,
    StateFilterSerializer,
)
from .serializers import (
    CustomerRegisterSerializer,
    CustomerLoginSerializer,
    CustomerLoginConfirmationSerializer,
    CustomerPhoneConfirmationSerializer,
    CustomerPasswordForgotSerializer,
    CustomerPasswordForgotConfirmationSerializer,
    CustomerProfileSerializer,
    CustomerUpdateSerializer,
    CustomerPasswordChangeSerializer,
    CustomerAddressSerializer,
    CustomerPreferenceSerializer,
)
from .services.auth_service import (
    CustomerAuthService,
    CustomerConfirmationError,
    CustomerConfirmationThrottled,
    CustomerConfirmationUnavailable,
)
from .services.address_service import CustomerAddressService
from .models import CustomerPreference


class CustomerRegister(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        result = service.register(serializer.validated_data)

        return api_response(True, _("Registration successful."), result, status_code=201)


class CustomerLogin(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        try:
            result = service.request_login_confirmation(
                serializer.validated_data["phone"],
                serializer.validated_data["password"],
            )
        except CustomerConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        except CustomerConfirmationUnavailable as exc:
            raise ConfirmationDeliveryUnavailable() from exc
        except CustomerConfirmationError as exc:
            raise ValidationError(exc.errors) from exc

        return api_response(
            True,
            _("Confirmation code sent."),
            result,
            status_code=202,
        )


class ConfirmationDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = _("The confirmation code could not be sent.")
    default_code = "confirmation_delivery_unavailable"


class CustomerLoginConfirmation(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerLoginConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = CustomerAuthService().confirm_login(**serializer.validated_data)
        except CustomerConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Login successful."), result)


class CustomerPasswordForgot(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerPasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = CustomerAuthService().request_password_reset(
                serializer.validated_data["phone"]
            )
        except CustomerConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        return api_response(
            True,
            _("If an eligible account exists, a confirmation code has been sent."),
            result,
            status_code=202,
        )


class CustomerPasswordForgotConfirmation(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CustomerPasswordForgotConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        values.pop("new_password_confirmation")
        try:
            CustomerAuthService().reset_password(**values)
        except CustomerConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Password reset successful."), None)


class CustomerPhoneConfirmationRequest(APIView):
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            result = CustomerAuthService().request_phone_confirmation(request.user)
        except CustomerConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        except CustomerConfirmationUnavailable as exc:
            raise ConfirmationDeliveryUnavailable() from exc
        except CustomerConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Confirmation code sent."), result, status_code=202)


class CustomerPhoneConfirmationVerify(APIView):
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CustomerPhoneConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = CustomerAuthService().confirm_phone(
                request.user,
                **serializer.validated_data,
            )
        except CustomerConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Phone number verified."), result)


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

        return api_response(True, _("Profile updated."), result)


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

        return api_response(True, _("Address created."), result, status_code=201)


class CustomerAddressDetail(APIView):
    permission_classes = [IsAuthenticated]

    def _get_address(self, customer, address_id):
        service = CustomerAddressService()
        address = service.get_for_customer(customer, address_id)
        if address is None:
            raise NotFound(_("Address not found."))
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

        return api_response(True, _("Address updated."), result)

    def delete(self, request, address_id):
        address = self._get_address(request.user, address_id)
        service = CustomerAddressService()
        service.delete(address)
        return api_response(True, _("Address deleted."), None)


class CustomerPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        preference, created = CustomerPreference.objects.get_or_create(customer=request.user)
        serializer = CustomerPreferenceSerializer(preference)
        return api_response(True, "", serializer.data)

    def patch(self, request):
        preference, created = CustomerPreference.objects.get_or_create(customer=request.user)
        serializer = CustomerPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(True, _("Preferences updated."), serializer.data)


class CustomerChangePassword(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CustomerPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CustomerAuthService()
        service.change_password(
            request.user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )

        return api_response(True, _("Password changed."))


class CustomerCountryOptions(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        countries = Country.objects.order_by("fa_title", "name")
        return api_response(data=CountryOptionSerializer(countries, many=True).data)


class CustomerStateOptions(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = CountryFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        states = State.objects.filter(
            country_id=query.validated_data["country_id"]
        ).order_by("fa_title", "name")
        return api_response(data=StateOptionSerializer(states, many=True).data)


class CustomerCityOptions(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = StateFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        cities = City.objects.filter(
            state_id=query.validated_data["state_id"]
        ).order_by("fa_title", "name")
        return api_response(data=CityOptionSerializer(cities, many=True).data)
