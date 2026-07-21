from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from core.responses import api_response
from .serializers import CustomerRegisterSerializer, CustomerLoginSerializer, CustomerProfileSerializer
from .services.auth_service import CustomerAuthService


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
