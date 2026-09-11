from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import APIException, NotFound, Throttled, ValidationError
from core.responses import api_response
from domains.vendor.auth import VendorJWTAuthentication
from .serializers import (
    VendorRegisterSerializer,
    VendorLoginSerializer,
    VendorLoginConfirmationSerializer,
    VendorPhoneConfirmationSerializer,
    VendorPasswordForgotSerializer,
    VendorPasswordForgotConfirmationSerializer,
    VendorProfileSerializer,
    VendorUpdateSerializer,
    VendorPasswordChangeSerializer,
    VendorPreferenceSerializer,
)
from .services.auth_service import (
    VendorAuthService,
    VendorConfirmationError,
    VendorConfirmationThrottled,
    VendorConfirmationUnavailable,
)
from .models import VendorPreference


class VendorRegister(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VendorRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = VendorAuthService()
        result = service.register(serializer.validated_data)

        return api_response(True, _("Registration successful."), result, status_code=201)


class VendorLogin(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VendorLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = VendorAuthService()
        try:
            result = service.request_login_confirmation(
                serializer.validated_data["phone"],
                serializer.validated_data["password"],
            )
        except VendorConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        except VendorConfirmationUnavailable as exc:
            raise ConfirmationDeliveryUnavailable() from exc
        except VendorConfirmationError as exc:
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


class VendorLoginConfirmation(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VendorLoginConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = VendorAuthService().confirm_login(**serializer.validated_data)
        except VendorConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Login successful."), result)


class VendorPasswordForgot(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VendorPasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = VendorAuthService().request_password_reset(
                serializer.validated_data["phone"]
            )
        except VendorConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        return api_response(
            True,
            _("If an eligible account exists, a confirmation code has been sent."),
            result,
            status_code=202,
        )


class VendorPasswordForgotConfirmation(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VendorPasswordForgotConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data.copy()
        values.pop("new_password_confirmation")
        try:
            VendorAuthService().reset_password(**values)
        except VendorConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Password reset successful."), None)


class VendorPhoneConfirmationRequest(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            result = VendorAuthService().request_phone_confirmation(request.user)
        except VendorConfirmationThrottled as exc:
            raise Throttled(wait=exc.retry_after) from exc
        except VendorConfirmationUnavailable as exc:
            raise ConfirmationDeliveryUnavailable() from exc
        except VendorConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Confirmation code sent."), result, status_code=202)


class VendorPhoneConfirmationVerify(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VendorPhoneConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = VendorAuthService().confirm_phone(
                request.user,
                **serializer.validated_data,
            )
        except VendorConfirmationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, _("Phone number verified."), result)


class VendorMe(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = VendorProfileSerializer(request.user)
        return api_response(True, "", serializer.data)

    def patch(self, request):
        serializer = VendorUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        service = VendorAuthService()
        result = service.update_profile(request.user, serializer.validated_data)

        return api_response(True, _("Profile updated."), result)


class VendorChangePassword(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VendorPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = VendorAuthService()
        service.change_password(
            request.user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )

        return api_response(True, _("Password changed."))


class VendorPreferenceView(APIView):
    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        preference, created = VendorPreference.objects.get_or_create(vendor=request.user)
        serializer = VendorPreferenceSerializer(preference)
        return api_response(True, "", serializer.data)

    def patch(self, request):
        preference, created = VendorPreference.objects.get_or_create(vendor=request.user)
        serializer = VendorPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(True, _("Preferences updated."), serializer.data)
